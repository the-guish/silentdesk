from __future__ import annotations

from collections.abc import Mapping

from ....contract import AuthError, Connector, Message, ServiceStatus, SyncResult, UnknownTopic, Unsupported
from ..core import gmail
from ..domain.state import GmailState
from ..ports.authorization import Authorization
from ..ports.credentials import Credentials
from ..ports.gmail_api import GmailApi
from ..ports.state_store import StateStore

# Messages read between two saves, so an interrupted first sync resumes
# where it stopped. Each batch also gets a fresh access token, which lasts
# an hour.
SAVE_EVERY = 500


class Gmail(Connector):
    """The Gmail Inbox: one topic per thread, its messages as items. Replies
    go to the thread's newest message, and deleting moves the thread to the
    trash. Messages stay after they leave the Inbox."""

    def __init__(
        self, api: GmailApi, authorization: Authorization, credentials: Credentials, state: StateStore
    ) -> None:
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state

    @property
    def service(self) -> str:
        return gmail.SERVICE

    async def status(self) -> ServiceStatus:
        if self.credentials.refresh_token() is None:
            return ServiceStatus(self.service, self.authorization.configured, connected=False, account=None)
        state = await self.state.load()
        return ServiceStatus(
            self.service, self.authorization.configured, connected=True, account=state.email if state else None
        )

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        """Signs in through the browser and keeps the refresh token. Another
        account's messages are forgotten; an older grant is revoked."""
        grant = await self.authorization.sign_in(gmail.SCOPES, gmail.SCOPES)
        email = (await self.api.profile(grant.access_token)).email
        old = self.credentials.refresh_token()
        if old is not None and old != grant.refresh_token:
            await self.authorization.revoke(old)
        state = await self.state.load()
        if state is None or state.email != email:
            await self.state.clear()
            state = GmailState(email, None)
        self.credentials.save_refresh_token(grant.refresh_token)
        await self.state.save(state)
        return await self.status()

    async def disconnect(self) -> ServiceStatus:
        """Revokes the grant at Google, then forgets it, the account and every message."""
        token = self.credentials.refresh_token()
        if token is not None:
            await self.authorization.revoke(token)
        self.credentials.delete_refresh_token()
        await self.state.clear()
        return await self.status()

    async def _access_token(self) -> str:
        refresh = self.credentials.refresh_token()
        if refresh is None or await self.state.load() is None:
            raise AuthError(self.service, "Gmail is not connected.")
        try:
            return await self.authorization.access_token(refresh)
        except AuthError as error:
            if self.authorization.configured:
                # The grant is gone: forget it, keep the messages and topics.
                self.credentials.delete_refresh_token()
            raise AuthError(self.service, f"{error} Connect Gmail again.") from error

    async def sync(self) -> SyncResult:
        """The first sync lists the whole Inbox; later ones list only what
        entered it since, until Gmail's history runs out (about a week)."""
        access = await self._access_token()
        state = await self.state.load()
        assert state is not None
        changes = await self.api.inbox_changes(access, state.history_id) if state.history_id else None
        if changes is not None:
            ids, history_id = changes
        else:
            # Take the marker first, so changes made while listing come next time.
            history_id = (await self.api.profile(access)).history_id
            ids = await self.api.inbox_ids(access)
        ids = gmail.new_ids(await self.state.known_ids(), ids)

        touched: set[str] = set()
        for offset in range(0, len(ids), SAVE_EVERY):
            if offset:
                access = await self._access_token()
            messages = await self.api.messages(access, ids[offset : offset + SAVE_EVERY], lambda done: None)
            await self.state.add_messages(messages)
            touched |= {message.thread_id for message in messages}
        await self.state.save(GmailState(state.email, history_id))

        # After a full listing, every stored thread: an interrupted sync may
        # have stored messages the desk has not seen.
        threads = await self.state.threads(None if changes is None else sorted(touched))
        return SyncResult(
            [gmail.topic(thread_id, messages) for thread_id, messages in threads.items()], removed=[], complete=False
        )

    async def reply(self, topic_key: str, body: str) -> None:
        """Sends `body`, typed by the user, as a reply to the thread's newest
        message. It joins the thread; no AI notice, as the user wrote it."""
        thread = (await self.state.threads([topic_key])).get(topic_key)
        if not thread:
            raise UnknownTopic(f"Gmail has no synced thread {topic_key!r}.")
        newest = max(thread, key=lambda message: (message.date, message.message_id))
        access = await self._access_token()
        original = await self.api.original(access, newest.message_id)
        await self.api.send(access, topic_key, gmail.reply(original, body))

    async def history(self, topic_key: str) -> list[Message]:
        raise Unsupported(self.service, "SilentDesk shows Gmail's headers only; it never reads a message's body.")

    async def delete_topic(self, topic_key: str) -> None:
        """Moves the thread to the Gmail trash and forgets its messages."""
        access = await self._access_token()
        await self.api.trash_thread(access, topic_key)
        await self.state.remove_thread(topic_key)
