from __future__ import annotations

from collections.abc import Mapping

from ....contract import AuthError, Connector, Message, ServiceStatus, SyncResult, Topic, Unsupported
from ..core import tasks
from ..domain.state import GoogleState
from ..ports.authorization import Authorization
from ..ports.credentials import Credentials
from ..ports.state_store import StateStore
from ..ports.tasks_api import TasksApi


class GoogleTasks(Connector):
    """Every open task in Google Tasks, read-only: one topic per task, with
    one item. Signs in with the Google client Gmail uses, but with its own
    read-only grant and refresh token."""

    def __init__(
        self, api: TasksApi, authorization: Authorization, credentials: Credentials, state: StateStore
    ) -> None:
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state

    @property
    def service(self) -> str:
        return tasks.SERVICE

    async def status(self) -> ServiceStatus:
        if self.credentials.refresh_token(self.service) is None:
            return ServiceStatus(self.service, self.authorization.configured, connected=False, account=None)
        state = await self.state.load(self.service)
        return ServiceStatus(
            self.service, self.authorization.configured, connected=True, account=state.email if state else None
        )

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        """Signs in through the browser for read-only access, then keeps the
        refresh token. A previous grant for another sign-in is revoked."""
        grant = await self.authorization.sign_in(tasks.SCOPES, tasks.REQUIRED_SCOPES)
        email = await self.api.email(grant.access_token)
        old = self.credentials.refresh_token(self.service)
        if old is not None and old != grant.refresh_token:
            await self.authorization.revoke(old)
        self.credentials.save_refresh_token(self.service, grant.refresh_token)
        await self.state.save(self.service, GoogleState(email))
        return await self.status()

    async def disconnect(self) -> ServiceStatus:
        """Revokes the grant at Google, then forgets the token and the account."""
        token = self.credentials.refresh_token(self.service)
        if token is not None:
            await self.authorization.revoke(token)
        self.credentials.delete_refresh_token(self.service)
        await self.state.clear(self.service)
        return await self.status()

    async def sync(self) -> SyncResult:
        refresh = self.credentials.refresh_token(self.service)
        if refresh is None:
            raise AuthError(self.service, "Google Tasks is not connected.")
        try:
            access = await self.authorization.access_token(refresh)
        except AuthError as error:
            if self.authorization.configured:
                # The grant is gone: forget it, keep the topics.
                self.credentials.delete_refresh_token(self.service)
            raise AuthError(self.service, f"{error} Connect Google Tasks again.") from error
        found = []
        for task_list in await self.api.lists(access):
            found += await self.api.tasks(access, task_list)
        return SyncResult([tasks.topic(task) for task in found if tasks.is_open(task)], removed=[], complete=True)

    async def reply(self, topic_key: str, body: str) -> None:
        raise Unsupported(self.service, "SilentDesk cannot reply to a task.")

    async def history(self, topic_key: str) -> list[Message]:
        raise Unsupported(self.service, "Google Tasks has no conversation to show.")

    async def delete_topic(self, topic_key: str) -> None:
        raise Unsupported(self.service, "SilentDesk has read-only access to Google Tasks.")

    async def delete_item(self, topic_key: str, item_key: str) -> Topic | None:
        raise Unsupported(self.service, "SilentDesk has read-only access to Google Tasks.")
