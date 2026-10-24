from __future__ import annotations

from collections.abc import Mapping

from ....contract import Connector, ServiceStatus, SyncResult
from ..ports.authorization import Authorization
from ..ports.credentials import Credentials
from ..ports.state_store import StateStore
from ..ports.tasks_api import TasksApi


class GoogleTasks(Connector):
    """Every open task in Google Tasks, read-only: one topic per task, with one
    item. Replying and deleting raise `Unsupported` until the app asks for
    write access."""

    def __init__(
        self, api: TasksApi, authorization: Authorization, credentials: Credentials, state: StateStore
    ) -> None:
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state

    @property
    def service(self) -> str:
        return "tasks"

    async def status(self) -> ServiceStatus:
        if self.credentials.refresh_token(self.service) is None:
            return ServiceStatus(self.service, self.authorization.configured, connected=False, account=None)
        state = await self.state.load(self.service)
        return ServiceStatus(
            self.service, self.authorization.configured, connected=True, account=state.email if state else None
        )

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        raise NotImplementedError

    async def disconnect(self) -> ServiceStatus:
        raise NotImplementedError

    async def sync(self) -> SyncResult:
        raise NotImplementedError

    async def reply(self, topic_key: str, body: str) -> None:
        raise NotImplementedError

    async def delete_topic(self, topic_key: str) -> None:
        raise NotImplementedError
