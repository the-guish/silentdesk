"""Slack sign-in for a desktop (public) client: OAuth v2 with PKCE and a
`localhost` redirect. The Slack app must have PKCE enabled, so no client
secret exists. Only user scopes are requested; desktop redirects cannot
request bot scopes."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from ...adapters import oauth
from ...adapters.http import send
from ...core import errors
from ...core.ports import Config
from .api import SERVICE, field

AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
ACCESS_URL = "https://slack.com/api/oauth.v2.access"
REVOKE_URL = "https://slack.com/api/auth.revoke"

# `search:read` finds recent direct messages; `users:read` turns user IDs
# into names. Nothing is written to Slack.
USER_SCOPES = ("search:read", "users:read", "im:history", "mpim:history")

DEFAULT_REDIRECT_PORT = 47615
CALLBACK_PATH = "/slack/callback"
PORT_VAR = "SILENTDESK_SLACK_REDIRECT_PORT"

# Refresh a little before the access token actually expires.
EXPIRY_MARGIN_SECS = 60

_PORT = re.compile(r"\+?[0-9]+")


@dataclass(frozen=True)
class SlackClient:
    """The Slack app the organization (or user) created. Rust reads it from
    the environment, or from what was baked in at build time."""

    client_id: str
    redirect_port: int

    @classmethod
    def from_config(cls, config: Config) -> SlackClient | None:
        client_id = config.slack_client_id
        if client_id is None or not client_id.strip():
            return None
        port = (config.slack_redirect_port or "").strip()
        redirect_port = int(port) if _PORT.fullmatch(port) and int(port) <= 0xFFFF else DEFAULT_REDIRECT_PORT
        return cls(client_id, redirect_port)


@dataclass
class Credential:
    """What is kept in the OS credential store. Without token rotation Slack
    issues a long-lived user token; with rotation, a 12-hour access token
    plus a refresh token."""

    access_token: str
    refresh_token: str | None
    # Unix seconds.
    expires_at: int | None

    def needs_refresh(self, now: int) -> bool:
        return (
            self.refresh_token is not None
            and self.expires_at is not None
            and now >= self.expires_at - EXPIRY_MARGIN_SECS
        )

    def to_json(self) -> str:
        """The stored form, byte for byte what the Rust version wrote."""
        return json.dumps(
            {"access_token": self.access_token, "refresh_token": self.refresh_token, "expires_at": self.expires_at},
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> Credential | None:
        """`None` when the stored value cannot be read."""
        try:
            obj = json.loads(raw)
            return cls(
                access_token=field(obj, "access_token", str),
                refresh_token=field(obj, "refresh_token", (str, type(None)), None),
                expires_at=field(obj, "expires_at", (int, type(None)), None),
            )
        except ValueError:
            return None


def now() -> int:
    return int(time.time())


@dataclass
class AuthedUser:
    access_token: str | None
    refresh_token: str | None
    expires_in: int | None
    scope: str


@dataclass
class AccessResponse:
    ok: bool
    error: str | None
    # Present on refresh responses.
    access_token: str | None
    refresh_token: str | None
    expires_in: int | None
    # Present on the initial exchange for user tokens.
    authed_user: AuthedUser | None

    @classmethod
    def parse(cls, body: Any) -> AccessResponse:
        opt_str, opt_int = (str, type(None)), (int, type(None))
        user = field(body, "authed_user", (dict, type(None)), None)
        return cls(
            ok=field(body, "ok", bool),
            error=field(body, "error", opt_str, None),
            access_token=field(body, "access_token", opt_str, None),
            refresh_token=field(body, "refresh_token", opt_str, None),
            expires_in=field(body, "expires_in", opt_int, None),
            authed_user=None
            if user is None
            else AuthedUser(
                access_token=field(user, "access_token", opt_str, None),
                refresh_token=field(user, "refresh_token", opt_str, None),
                expires_in=field(user, "expires_in", opt_int, None),
                scope=field(user, "scope", str, ""),
            ),
        )

    def credential(self, now: int) -> tuple[Credential, str] | None:
        """The user token, wherever this response carries it."""
        u = self.authed_user
        if u is not None and u.access_token is not None:
            access, refresh, expires_in, scope = u.access_token, u.refresh_token, u.expires_in, u.scope
        else:
            access, refresh, expires_in, scope = self.access_token, self.refresh_token, self.expires_in, ""
        if access is None:
            return None
        return (
            Credential(access, refresh, None if expires_in is None else now + expires_in),
            scope,
        )


def authorization_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    query = urlencode(
        [
            ("client_id", client_id),
            ("user_scope", ",".join(USER_SCOPES)),
            ("redirect_uri", redirect_uri),
            ("state", state),
            ("code_challenge", challenge),
            ("code_challenge_method", "S256"),
        ]
    )
    return f"{AUTHORIZE_URL}?{query}"


async def authorize(
    http: httpx.AsyncClient,
    client: SlackClient,
    open_browser: Callable[[str], Awaitable[None]],
) -> Credential:
    """Runs the full sign-in: opens the browser via `open_browser`, waits for
    Slack to redirect back to the loopback listener, and exchanges the
    code."""
    loopback = await oauth.Loopback.fixed(client.redirect_port, CALLBACK_PATH, PORT_VAR)
    redirect_uri = loopback.redirect_uri
    pkce = oauth.pkce()
    state = oauth.state()

    try:
        await open_browser(authorization_url(client.client_id, redirect_uri, pkce.challenge, state))
    except BaseException:
        loopback.close()
        raise
    code = await loopback.wait_for_code(state)

    response = await access(
        http,
        {
            "grant_type": "authorization_code",
            "client_id": client.client_id,
            "code": code,
            "code_verifier": pkce.verifier,
            "redirect_uri": redirect_uri,
        },
        client,
    )
    got = response.credential(now())
    if got is None:
        raise errors.Auth("Slack did not return a user token.")
    credential, scope = got

    granted = [s.strip() for s in scope.split(",")]
    if not all(s in granted for s in USER_SCOPES):
        raise errors.Auth("Slack access was not fully granted.")
    return credential


async def refresh(http: httpx.AsyncClient, client: SlackClient, credential: Credential) -> Credential:
    """Swaps the refresh token for a new access token. With token rotation,
    Slack also returns a new refresh token, which replaces the old one."""
    if credential.refresh_token is None:
        raise errors.Reauthorize(SERVICE)
    response = await access(
        http,
        {
            "grant_type": "refresh_token",
            "client_id": client.client_id,
            "refresh_token": credential.refresh_token,
        },
        client,
    )
    got = response.credential(now())
    if got is None:
        raise errors.Reauthorize(SERVICE)
    fresh, _ = got
    if fresh.refresh_token is None:
        fresh.refresh_token = credential.refresh_token
    return fresh


async def revoke(http: httpx.AsyncClient, access_token: str) -> None:
    """Asks Slack to invalidate the token. Best effort: the local copy is
    deleted either way."""
    try:
        await send(http, "POST", REVOKE_URL, headers={"Authorization": f"Bearer {access_token}"})
    except errors.AppError:
        pass


async def access(http: httpx.AsyncClient, form: dict[str, str], client: SlackClient) -> AccessResponse:
    raw = await send(http, "POST", ACCESS_URL, data=form)
    try:
        response = AccessResponse.parse(raw.json())
    except ValueError:
        raise errors.Network("error decoding response body") from None
    if response.ok:
        return response
    error = response.error if response.error is not None else "unknown_error"
    if error in ("invalid_grant", "invalid_refresh_token", "token_expired", "token_revoked"):
        raise errors.Reauthorize(SERVICE)
    if error in ("invalid_client_id", "bad_client_secret", "invalid_client"):
        raise errors.Auth(
            "Slack rejected the app. Check SILENTDESK_SLACK_CLIENT_ID, and that PKCE is enabled for the Slack app."
        )
    if error in ("invalid_code", "code_already_used"):
        raise errors.Auth("the sign-in code was invalid or expired. Try again.")
    if error == "bad_redirect_uri":
        raise errors.Auth(
            "the Slack app's redirect URL does not match. "
            f"Add http://localhost:{client.redirect_port}{CALLBACK_PATH} to it."
        )
    raise errors.Auth(f"Slack returned {error}.")
