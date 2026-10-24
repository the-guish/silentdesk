"""The Slack source: connect, sync and disconnect, as the UI calls them."""

from __future__ import annotations

from typing import Any

from ...core import errors
from ...core.model import SlackAccount, VaultData
from ...core.secret_names import SLACK_CREDENTIAL
from ...core.topics import now_rfc3339, topic_views
from ..base import Method, ServiceStatus, Source
from . import api, domain, oauth
from .api import SERVICE

# How many recent messages the topic screen shows per conversation.
HISTORY_COUNT = 50


def account_label(a: SlackAccount) -> str:
    return f"{a.user_name} · {a.team_name}"


class SlackSource(Source):
    name = "slack"

    def _client(self) -> oauth.SlackClient:
        client = oauth.SlackClient.from_config(self.host.config)
        if client is None:
            raise errors.NotConfigured(SERVICE, "SILENTDESK_SLACK_CLIENT_ID", "slack")
        return client

    def _load_credential(self) -> oauth.Credential | None:
        raw = self.host.secrets.get(SLACK_CREDENTIAL)
        return None if raw is None else oauth.Credential.from_json(raw)

    async def _store_credential(self, credential: oauth.Credential) -> None:
        await self.host.secrets.set(SLACK_CREDENTIAL, credential.to_json())

    async def _open_browser(self, url: str) -> None:
        try:
            await self.host.browser.open(url)
        except errors.Host:
            raise errors.Auth("could not open your web browser.") from None

    async def status(self) -> ServiceStatus:
        stored = (await self.host.store.read()).slack_account
        account = None if stored is None else account_label(stored)
        connected = account is not None and self._load_credential() is not None
        return ServiceStatus(
            configured=oauth.SlackClient.from_config(self.host.config) is not None,
            connected=connected,
            account=account,
        )

    async def _fresh_credential(self, client: oauth.SlackClient) -> oauth.Credential:
        """A credential that is valid now, refreshed and re-stored if it had
        expired. A dead grant is forgotten so the UI offers to connect
        again."""
        credential = self._load_credential()
        if credential is None:
            raise errors.NotConnected(SERVICE)
        if not credential.needs_refresh(oauth.now()):
            return credential
        try:
            fresh = await oauth.refresh(self.http, client, credential)
        except errors.Reauthorize:
            await self.host.secrets.delete(SLACK_CREDENTIAL)
            raise
        await self._store_credential(fresh)
        return fresh

    async def connect(self, params: dict[str, Any]) -> ServiceStatus:
        """Signs in through the system browser and stores the token in the
        OS keychain. Switching to a different user or workspace drops the
        old account's local data."""
        client = self._client()

        credential = await oauth.authorize(self.http, client, self._open_browser)
        me = await api.identity(self.http, credential.access_token)

        old = self._load_credential()
        if old is not None and old.access_token != credential.access_token:
            await oauth.revoke(self.http, old.access_token)
        await self._store_credential(credential)

        def change(data: VaultData) -> None:
            a = data.slack_account
            same_account = a is not None and a.user_id == me.user_id and a.team_id == me.team_id
            if not same_account:
                domain.clear(data)
            data.slack_account = SlackAccount(
                user_id=me.user_id,
                user_name=me.user_name,
                team_id=me.team_id,
                team_name=me.team_name,
            )

        await self.host.store.update(change)
        return await self.status()

    async def sync(self) -> list[dict[str, Any]]:
        """Pulls the most recent direct messages and maps each one to a
        topic."""
        client = self._client()

        account = (await self.host.store.read()).slack_account
        if account is None:
            raise errors.NotConnected(SERVICE)
        credential = await self._fresh_credential(client)
        try:
            latest = await api.recent_direct_messages(
                self.http, credential.access_token, account.user_id, domain.SYNC_COUNT
            )
        except errors.Reauthorize:
            await self.host.secrets.delete(SLACK_CREDENTIAL)
            raise
        now = now_rfc3339()

        def change(data: VaultData) -> list[dict[str, Any]]:
            domain.apply_sync(data, latest, now)
            return topic_views(data)

        return await self.host.store.update(change)

    def actions(self) -> dict[str, Method]:
        async def history(params: dict[str, Any]) -> list[api.ConversationMessage]:
            async with self.op:
                return await self.history(str(params.get("topicId", "")))

        return {"history": history}

    async def history(self, topic_id: str) -> list[api.ConversationMessage]:
        """The recent messages of the topic's conversation, read live from
        Slack, oldest first. Nothing is stored."""
        client = self._client()
        data = await self.host.store.read()
        if data.slack_account is None:
            raise errors.NotConnected(SERVICE)
        channels = sorted({m.channel_id for m in data.slack_messages if m.topic_id == topic_id})
        if not channels:
            raise errors.AppError("This topic has no Slack conversation any more. Go back to the list.")
        credential = await self._fresh_credential(client)
        messages: list[api.ConversationMessage] = []
        try:
            for channel in channels:
                messages += await api.conversation(
                    self.http, credential.access_token, data.slack_account.user_id, channel, HISTORY_COUNT
                )
        except errors.Reauthorize:
            await self.host.secrets.delete(SLACK_CREDENTIAL)
            raise
        messages.sort(key=lambda m: api.ts_value(m.ts))
        return messages

    async def disconnect(self) -> ServiceStatus:
        """Revokes the token at Slack, deletes it and all local Slack
        data."""
        credential = self._load_credential()
        if credential is not None:
            # An expired access token cannot revoke itself; renew it first.
            client = oauth.SlackClient.from_config(self.host.config)
            if credential.needs_refresh(oauth.now()) and client is not None:
                try:
                    credential = await oauth.refresh(self.http, client, credential)
                except errors.AppError:
                    pass
            await oauth.revoke(self.http, credential.access_token)
        await self.host.secrets.delete(SLACK_CREDENTIAL)
        await self.host.store.update(domain.clear)
        return await self.status()
