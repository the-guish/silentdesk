"""Google sign-in for Gmail, through the shared OAuth sign-in."""

from __future__ import annotations

from collections.abc import Sequence

from ....contract import AuthError, NetworkError, OAuth, OAuthClient
from ..domain.gmail import Grant
from ..ports.authorization import Authorization

SERVICE = "gmail"


class GoogleAuthorization(Authorization):
    def __init__(self, oauth: OAuth, client: OAuthClient | None, revoke_url: str) -> None:
        self.oauth = oauth
        # None when no Google client ID is configured.
        self.client = client
        self.revoke_url = revoke_url

    @property
    def configured(self) -> bool:
        return self.client is not None

    def _client(self) -> OAuthClient:
        if self.client is None:
            raise AuthError(SERVICE, "Gmail is not configured: set SILENTDESK_GOOGLE_CLIENT_ID.")
        return self.client

    async def sign_in(self, scopes: Sequence[str], required: Sequence[str]) -> Grant:
        tokens = await self.oauth.sign_in(self._client(), scopes)
        if not all(scope in tokens.scopes for scope in required):
            raise AuthError(SERVICE, "Gmail access was not granted.")
        if not tokens.access_token or not tokens.refresh_token:
            raise AuthError(SERVICE, "Google did not return a refresh token.")
        return Grant(tokens.access_token, tokens.refresh_token)

    async def access_token(self, refresh_token: str) -> str:
        tokens = await self.oauth.refresh(self._client(), refresh_token)
        if not tokens.access_token:
            raise NetworkError(SERVICE, "Google returned no access token.")
        return tokens.access_token

    async def revoke(self, refresh_token: str) -> None:
        await self.oauth.revoke(self.revoke_url, refresh_token)
