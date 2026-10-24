"""Google sign-in: authorization code flow with PKCE and a loopback redirect
on any free port. Shared by every Google service; each one asks for its
own grant and keeps its own refresh token."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from ...adapters import oauth
from ...adapters.http import send
from ...core import errors
from ...core.ports import Browser, Config
from . import wire

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


@dataclass(frozen=True)
class Grant:
    """What one SilentDesk service asks Google for."""

    # Named in errors, e.g. "Gmail access was not granted."
    service: str
    # Requested at sign-in.
    scopes: tuple[str, ...]
    # Must all be granted; the user can untick scopes on Google's consent
    # screen.
    required: tuple[str, ...]


# `gmail.modify` reads headers and moves messages to the trash; it cannot
# delete them for good. `gmail.send` sends replies.
GMAIL = Grant(
    service="Gmail",
    scopes=(
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ),
    required=(
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ),
)


def _setting(value: str | None) -> str | None:
    """Empty values count as unset."""
    return value if value is not None and value.strip() else None


@dataclass(frozen=True)
class OAuthClient:
    """The OAuth client the organization registered in Google Cloud, from
    the app's configuration."""

    client_id: str
    # Google issues a secret for desktop clients but does not treat it as
    # confidential; PKCE protects the flow.
    client_secret: str | None = None

    @classmethod
    def from_config(cls, config: Config) -> OAuthClient | None:
        client_id = _setting(config.google_client_id)
        if client_id is None:
            return None
        return cls(client_id, _setting(config.google_client_secret))


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class _TokenResponse:
    access_token: str
    refresh_token: str | None
    scope: str


def _token_response(value: Any) -> _TokenResponse:
    o = wire.obj(value)
    return _TokenResponse(
        access_token=wire.string(o, "access_token"),
        refresh_token=wire.opt_string(o, "refresh_token"),
        scope=wire.string(o, "scope", ""),
    )


def authorization_url(client: OAuthClient, grant: Grant, redirect_uri: str, challenge: str, state: str) -> str:
    query = [
        ("client_id", client.client_id),
        ("redirect_uri", redirect_uri),
        ("response_type", "code"),
        ("scope", " ".join(grant.scopes)),
        ("code_challenge", challenge),
        ("code_challenge_method", "S256"),
        ("state", state),
        ("access_type", "offline"),
        ("prompt", "consent"),
    ]
    return f"{AUTH_URL}?{urlencode(query)}"


def browser_opener(browser: Browser) -> Callable[[str], Awaitable[None]]:
    """Opens the sign-in page in the system browser."""

    async def open_browser(url: str) -> None:
        try:
            await browser.open(url)
        except errors.AppError:
            raise errors.Auth("could not open your web browser.") from None

    return open_browser


async def authorize(
    http: httpx.AsyncClient,
    client: OAuthClient,
    grant: Grant,
    open_browser: Callable[[str], Awaitable[None]],
) -> Tokens:
    """Runs the full sign-in: opens the browser via `open_browser`, waits for
    Google to redirect back to the loopback listener, and exchanges the
    code."""
    loopback = await oauth.Loopback.any_port()
    try:
        redirect_uri = loopback.redirect_uri
        pkce = oauth.pkce()
        state = oauth.state()

        await open_browser(authorization_url(client, grant, redirect_uri, pkce.challenge, state))
        code = await loopback.wait_for_code(state)
    finally:
        loopback.close()

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": pkce.verifier,
        "redirect_uri": redirect_uri,
        "client_id": client.client_id,
    }
    if client.client_secret is not None:
        form["client_secret"] = client.client_secret
    token = await _token_request(http, form, grant.service)

    granted = token.scope.split()
    if not all(s in granted for s in grant.required):
        raise errors.Auth(f"{grant.service} access was not granted.")
    if token.refresh_token is None:
        raise errors.Auth("Google did not return a refresh token.")
    return Tokens(token.access_token, token.refresh_token)


async def access_token(http: httpx.AsyncClient, client: OAuthClient, grant: Grant, refresh_token: str) -> str:
    """Exchanges a refresh token for a short-lived access token."""
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client.client_id,
    }
    if client.client_secret is not None:
        form["client_secret"] = client.client_secret
    return (await _token_request(http, form, grant.service)).access_token


async def revoke(http: httpx.AsyncClient, refresh_token: str) -> None:
    """Asks Google to invalidate the grant. Best effort: the local token is
    deleted either way."""
    try:
        await send(http, "POST", REVOKE_URL, data={"token": refresh_token})
    except errors.AppError:
        pass


async def _token_request(http: httpx.AsyncClient, form: dict[str, str], service: str) -> _TokenResponse:
    response = await send(http, "POST", TOKEN_URL, data=form)
    if response.is_success:
        return wire.read_json(response, _token_response)
    status = response.status_code
    try:
        error = wire.string(wire.obj(response.json()), "error")
    except (ValueError, wire.Malformed):
        error = "unknown_error"
    if error == "invalid_grant":
        raise errors.Reauthorize(service)
    if error in ("invalid_client", "unauthorized_client"):
        raise errors.Auth(
            "Google rejected the OAuth client. Check SILENTDESK_GOOGLE_CLIENT_ID and SILENTDESK_GOOGLE_CLIENT_SECRET."
        )
    raise errors.Auth(f"Google returned {error} ({status}).")
