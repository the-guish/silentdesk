"""Slack sign-in through the shared OAuth sign-in. The Slack app has PKCE
enabled, so there is no client secret; only user scopes are asked for."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from ....contract import AuthError, OAuth, OAuthClient, Tokens
from ..domain.slack import Credential
from ..ports.authorization import Authorization

SERVICE = "slack"
USER_SCOPES = ("search:read", "users:read", "im:history", "mpim:history")


class SlackAuthorization(Authorization):
    def __init__(self, oauth: OAuth, client: OAuthClient | None, revoke_url: str) -> None:
        self.oauth = oauth
        self.client = client
        self.revoke_url = revoke_url

    @property
    def configured(self) -> bool:
        return self.client is not None

    def _client(self) -> OAuthClient:
        if self.client is None:
            raise AuthError(SERVICE, "Slack is not configured: set SILENTDESK_SLACK_CLIENT_ID.")
        return self.client

    async def sign_in(self) -> Credential:
        client = self._client()
        credential, scope = _credential(await self.oauth.sign_in(client, USER_SCOPES), client)
        if not all(s in [g.strip() for g in scope.split(",")] for s in USER_SCOPES):
            raise AuthError(SERVICE, "Slack access was not fully granted.")
        return credential

    async def refresh(self, credential: Credential) -> Credential:
        if credential.refresh_token is None:
            raise AuthError(SERVICE, "The Slack token has expired.")
        fresh, _ = _credential(await self.oauth.refresh(self._client(), credential.refresh_token), self._client())
        # With token rotation, Slack may send a new refresh token; else keep the old one.
        return Credential(fresh.access_token, fresh.refresh_token or credential.refresh_token, fresh.expires_at)

    async def revoke(self, access_token: str) -> None:
        await self.oauth.revoke(self.revoke_url, access_token)


def _credential(tokens: Tokens, client: OAuthClient) -> tuple[Credential, str]:
    """The user token from Slack's answer, which reports errors with ok: false."""
    body: Mapping[str, Any] = tokens.raw
    if body.get("ok") is not True:
        error = body.get("error") or "unknown_error"
        if error in ("invalid_grant", "invalid_refresh_token", "token_expired", "token_revoked"):
            raise AuthError(SERVICE, "The Slack sign-in has expired or was revoked.")
        if error in ("invalid_client_id", "bad_client_secret", "invalid_client"):
            raise AuthError(SERVICE, "Slack rejected the app: check SILENTDESK_SLACK_CLIENT_ID, and that PKCE is on.")
        if error == "bad_redirect_uri":
            raise AuthError(
                SERVICE, f"Add http://localhost:{client.port}{client.path} to the Slack app's redirect URLs."
            )
        raise AuthError(SERVICE, f"Slack sign-in failed: {error}.")
    user = body.get("authed_user") if isinstance(body.get("authed_user"), dict) else {}
    # The first exchange puts the user token in authed_user; refreshes, at the top.
    source = user if user.get("access_token") else body
    access, refresh, expires_in = source.get("access_token"), source.get("refresh_token"), source.get("expires_in")
    if not isinstance(access, str):
        raise AuthError(SERVICE, "Slack did not return a user token.")
    expires_at = int(time.time()) + expires_in if isinstance(expires_in, int) else None
    return Credential(access, refresh if isinstance(refresh, str) else None, expires_at), str(user.get("scope", ""))
