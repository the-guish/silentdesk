from __future__ import annotations

from collections.abc import Mapping

from ....contract import AuthError, Connector, ServiceStatus, SyncResult
from ..ports.authorization import Authorization
from ..ports.credentials import Credentials
from ..ports.gmail_api import GmailApi
from ..ports.state_store import StateStore


class Gmail(Connector):
    """The Gmail inbox: one topic per thread. Replies go to the thread's newest
    message, and deleting moves the thread to the trash."""

    def __init__(
        self, api: GmailApi, authorization: Authorization, credentials: Credentials, state: StateStore
    ) -> None:
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state

    @property
    def service(self) -> str:
        return "gmail"

    async def status(self) -> ServiceStatus:
        if self.credentials.refresh_token() is None:
            return ServiceStatus(self.service, self.authorization.configured, connected=False, account=None)
        state = await self.state.load()
        return ServiceStatus(
            self.service, self.authorization.configured, connected=True, account=state.email if state else None
        )

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        raise NotImplementedError

    async def disconnect(self) -> ServiceStatus:
        """Forgets the refresh token and the account. Revoking the grant at
        Google comes with sign-in."""
        self.credentials.delete_refresh_token()
        await self.state.clear()
        return await self.status()

    async def sync(self) -> SyncResult:
        if self.credentials.refresh_token() is None:
            raise AuthError(self.service, "Gmail is not connected.")
        raise NotImplementedError

    async def reply(self, topic_key: str, body: str) -> None:
        raise NotImplementedError

    async def delete_topic(self, topic_key: str) -> None:
        raise NotImplementedError
