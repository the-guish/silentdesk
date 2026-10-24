"""OAuth with PKCE and a loopback redirect, the flow Google recommends for desktop apps."""

from __future__ import annotations

from collections.abc import Sequence

from ....contract import Browser, Http
from ..ports.authorization import Authorization, Grant


class LoopbackAuthorization(Authorization):
    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        http: Http,
        browser: Browser,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http
        self.browser = browser

    @property
    def configured(self) -> bool:
        return self.client_id is not None

    async def sign_in(self, scopes: Sequence[str]) -> Grant:
        raise NotImplementedError

    async def refresh(self, refresh_token: str) -> Grant:
        raise NotImplementedError

    async def revoke(self, token: str) -> None:
        raise NotImplementedError
