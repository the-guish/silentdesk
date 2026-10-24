"""Gmail as a source: sign-in, sync, trash and reply."""

from __future__ import annotations

from typing import Any

from ...core import errors
from ...core.model import GmailAccount, GmailMessage, VaultData
from ...core.secret_names import GMAIL_REFRESH_TOKEN
from ...core.topics import now_rfc3339, topic_views
from ..base import Method, ServiceStatus, Source
from . import api, domain, oauth, reply

SERVICE = "Gmail"

# Messages read between two saves of the data, so that an interrupted first
# sync resumes where it stopped. Each batch also gets a fresh access token,
# which expires after an hour.
SAVE_EVERY = 500
# Progress events are sent every this many messages.
PROGRESS_EVERY = 25


def _param(params: dict[str, Any], key: str, command: str) -> str:
    """A string argument of a call from the UI."""
    value = params.get(key)
    if not isinstance(value, str):
        raise errors.AppError(f"invalid args `{key}` for command `{command}`: expected a string")
    return value


class GmailSource(Source):
    name = "gmail"

    def google(self) -> oauth.OAuthClient:
        client = oauth.OAuthClient.from_config(self.host.config)
        if client is None:
            raise errors.NotConfigured(SERVICE, "SILENTDESK_GOOGLE_CLIENT_ID", "gmail")
        return client

    def refresh_token(self) -> str | None:
        return self.host.secrets.get(GMAIL_REFRESH_TOKEN)

    async def access_token(self) -> str:
        """A fresh access token for the connected account."""
        client = self.google()
        if (await self.host.store.read()).gmail_account is None:
            raise errors.NotConnected(SERVICE)
        refresh = self.refresh_token()
        if refresh is None:
            raise errors.NotConnected(SERVICE)
        try:
            return await oauth.access_token(self.http, client, oauth.GMAIL, refresh)
        except errors.Reauthorize:
            # The grant is dead. Forget it, but keep local topics so that
            # reconnecting the same account picks up where it left off.
            await self.host.secrets.delete(GMAIL_REFRESH_TOKEN)
            raise

    async def known_message(self, message_id: str) -> GmailMessage:
        """SilentDesk acts only on emails it has synced."""
        for m in (await self.host.store.read()).gmail_messages:
            if m.message_id == message_id:
                return m
        raise errors.UnknownMessage()

    async def status(self) -> ServiceStatus:
        account = (await self.host.store.read()).gmail_account
        email = account.email if account is not None else None
        return ServiceStatus(
            configured=oauth.OAuthClient.from_config(self.host.config) is not None,
            connected=email is not None and self.refresh_token() is not None,
            account=email,
        )

    async def connect(self, params: dict[str, Any]) -> ServiceStatus:
        """Signs in through the system browser and stores the refresh token
        in the OS keychain. Switching to a different account drops the old
        account's local data."""
        client = self.google()

        tokens = await oauth.authorize(self.http, client, oauth.GMAIL, oauth.browser_opener(self.host.browser))
        email = (await api.profile(self.http, tokens.access_token)).email_address

        old = self.refresh_token()
        if old is not None and old != tokens.refresh_token:
            await oauth.revoke(self.http, old)
        await self.host.secrets.set(GMAIL_REFRESH_TOKEN, tokens.refresh_token)

        def change(data: VaultData) -> None:
            same_account = data.gmail_account is not None and data.gmail_account.email == email
            if not same_account:
                domain.clear(data)
            data.gmail_account = GmailAccount(email)

        await self.host.store.update(change)
        return await self.status()

    async def sync(self) -> list[dict[str, Any]]:
        """Pulls the subject of every Inbox message SilentDesk does not have
        yet, each as a topic of its own. The first sync lists the whole
        Inbox; later ones list only what entered it since. Messages stay
        after they leave the Inbox."""
        self.google()
        access = await self.access_token()
        data = await self.host.store.read()

        changes = None
        if data.gmail_history_id is not None:
            changes = await api.inbox_changes(self.http, access, data.gmail_history_id)
        if changes is not None:
            ids, history_id = changes
        else:
            # Take the marker first, so changes made while listing are
            # picked up next time.
            history_id = (await api.profile(self.http, access)).history_id
            ids = await api.inbox_ids(self.http, access)
        ids = domain.new_ids(data, ids)
        del data

        total = len(ids)

        def report(done: int) -> None:
            self.host.events.emit("gmail-sync-progress", {"done": done, "total": total})

        report(0)
        save_every, progress_every = SAVE_EVERY, PROGRESS_EVERY
        for offset in range(0, total, save_every):
            chunk = ids[offset : offset + save_every]
            access = await self.access_token()

            def progress(n: int, offset: int = offset) -> None:
                if n % progress_every == 0:
                    report(offset + n)

            messages = await api.subjects(self.http, access, chunk, progress)
            now = now_rfc3339()
            await self.host.store.update(
                lambda data, messages=messages, now=now: domain.add_messages(data, messages, now)
            )
            report(offset + len(chunk))

        def finish(data: VaultData) -> list[dict[str, Any]]:
            data.gmail_history_id = history_id
            return topic_views(data)

        return await self.host.store.update(finish)

    async def trash(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Moves an email to the Gmail trash and drops it, with its topic,
        from SilentDesk."""
        message_id = _param(params, "messageId", "gmail_trash")
        async with self.op:
            await self.known_message(message_id)
            access = await self.access_token()
            await api.trash(self.http, access, message_id)

            def change(data: VaultData) -> list[dict[str, Any]]:
                domain.remove_message(data, message_id)
                return topic_views(data)

            return await self.host.store.update(change)

    async def reply(self, params: dict[str, Any]) -> None:
        """Sends `body`, typed by the user, as a reply in the email's
        thread. It appears in SilentDesk at the next sync."""
        message_id = _param(params, "messageId", "gmail_reply")
        body = _param(params, "body", "gmail_reply")
        if not body.strip():
            raise errors.EmptyReply()
        async with self.op:
            message = await self.known_message(message_id)
            access = await self.access_token()
            original = await api.original(self.http, access, message_id)
            raw = reply.build(original, body)
            await api.send(self.http, access, message.thread_id, raw)

    async def disconnect(self) -> ServiceStatus:
        """Revokes the grant at Google, deletes the token and all local
        Gmail data."""
        token = self.refresh_token()
        if token is not None:
            await oauth.revoke(self.http, token)
        await self.host.secrets.delete(GMAIL_REFRESH_TOKEN)
        await self.host.store.update(domain.clear)
        return await self.status()

    def actions(self) -> dict[str, Method]:
        return {"trash": self.trash, "reply": self.reply}
