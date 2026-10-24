"""Google Tasks as a source: sign-in and sync, read-only."""

from __future__ import annotations

from typing import Any

from ...core import errors
from ...core.model import TasksAccount, VaultData
from ...core.secret_names import GOOGLE_TASKS_REFRESH_TOKEN
from ...core.topics import now_rfc3339, topic_views
from ..base import ServiceStatus, Source
from ..gmail import oauth
from . import api, domain

SERVICE = "Google Tasks"


class TasksSource(Source):
    name = "tasks"

    def google(self) -> oauth.OAuthClient:
        """Google Tasks signs in with the same Google OAuth client as Gmail,
        but with its own read-only grant and refresh token."""
        client = oauth.OAuthClient.from_config(self.host.config)
        if client is None:
            raise errors.NotConfigured(SERVICE, "SILENTDESK_GOOGLE_CLIENT_ID", "google-tasks")
        return client

    def refresh_token(self) -> str | None:
        return self.host.secrets.get(GOOGLE_TASKS_REFRESH_TOKEN)

    async def status(self) -> ServiceStatus:
        account = (await self.host.store.read()).tasks_account
        email = account.email if account is not None else None
        return ServiceStatus(
            configured=oauth.OAuthClient.from_config(self.host.config) is not None,
            connected=email is not None and self.refresh_token() is not None,
            account=email,
        )

    async def connect(self, params: dict[str, Any]) -> ServiceStatus:
        """Signs in through the system browser for read-only access to Google
        Tasks, and stores the refresh token in the OS keychain. Switching to
        a different account drops the old account's local data."""
        client = self.google()

        tokens = await oauth.authorize(self.http, client, api.GRANT, oauth.browser_opener(self.host.browser))
        email = await api.email(self.http, tokens.access_token)

        old = self.refresh_token()
        if old is not None and old != tokens.refresh_token:
            await oauth.revoke(self.http, old)
        await self.host.secrets.set(GOOGLE_TASKS_REFRESH_TOKEN, tokens.refresh_token)

        def change(data: VaultData) -> None:
            same_account = data.tasks_account is not None and data.tasks_account.email == email
            if not same_account:
                domain.clear(data)
            data.tasks_account = TasksAccount(email)

        await self.host.store.update(change)
        return await self.status()

    async def sync(self) -> list[dict[str, Any]]:
        """Pulls every open task and maps each one to a topic."""
        client = self.google()

        if (await self.host.store.read()).tasks_account is None:
            raise errors.NotConnected(SERVICE)
        refresh = self.refresh_token()
        if refresh is None:
            raise errors.NotConnected(SERVICE)
        try:
            access = await oauth.access_token(self.http, client, api.GRANT, refresh)
        except errors.Reauthorize:
            # The grant is dead. Forget it, keep the topics.
            await self.host.secrets.delete(GOOGLE_TASKS_REFRESH_TOKEN)
            raise
        latest = await api.open_tasks(self.http, access)
        now = now_rfc3339()

        def change(data: VaultData) -> list[dict[str, Any]]:
            domain.apply_sync(data, latest, now)
            return topic_views(data)

        return await self.host.store.update(change)

    async def disconnect(self) -> ServiceStatus:
        """Revokes the grant at Google, deletes the token and all local task
        data."""
        token = self.refresh_token()
        if token is not None:
            await oauth.revoke(self.http, token)
        await self.host.secrets.delete(GOOGLE_TASKS_REFRESH_TOKEN)
        await self.host.store.update(domain.clear)
        return await self.status()
