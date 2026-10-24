from __future__ import annotations

from collections.abc import Mapping

from ....contract import Mail, ServiceStatus, SyncResult
from ..ports.authorization import Authorization
from ..ports.credentials import Credentials
from ..ports.gmail_api import GmailApi
from ..ports.state_store import StateStore


class Gmail(Mail):
    """The Gmail inbox as a mail connector: one topic per thread."""

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
        raise NotImplementedError

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        raise NotImplementedError

    async def disconnect(self) -> ServiceStatus:
        raise NotImplementedError

    async def sync(self) -> SyncResult:
        raise NotImplementedError

    async def reply(self, key: str, body: str) -> None:
        raise NotImplementedError

    async def trash(self, key: str) -> None:
        raise NotImplementedError
