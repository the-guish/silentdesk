from __future__ import annotations

import time
from collections.abc import Mapping

from ....contract import AuthError, Connector, Direction, Message, ServiceStatus, SyncResult, Topic, Unsupported
from ..core import slack
from ..domain.slack import Credential, DirectMessage, Match, SlackAccount
from ..ports.authorization import Authorization
from ..ports.credentials import Credentials
from ..ports.slack_api import SlackApi
from ..ports.state_store import StateStore


class Slack(Connector):
    """The most recent direct messages, sent and received, in 1:1 and group
    DMs: one topic per conversation. Read-only."""

    def __init__(
        self, api: SlackApi, authorization: Authorization, credentials: Credentials, state: StateStore
    ) -> None:
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state

    @property
    def service(self) -> str:
        return slack.SERVICE

    async def status(self) -> ServiceStatus:
        account = await self.state.load()
        connected = account is not None and self.credentials.load() is not None
        label = f"{account.user_name} · {account.team_name}" if account and connected else None
        return ServiceStatus(self.service, self.authorization.configured, connected=connected, account=label)

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        """Signs in through the browser, then keeps the token. An older token is revoked."""
        credential = await self.authorization.sign_in()
        account = await self.api.identity(credential.access_token)
        old = self.credentials.load()
        if old is not None and old.access_token != credential.access_token:
            await self.authorization.revoke(old.access_token)
        self.credentials.save(credential)
        await self.state.save(account)
        return await self.status()

    async def disconnect(self) -> ServiceStatus:
        """Revokes the token at Slack, renewing it first if it had expired,
        then forgets it and the account."""
        credential = self.credentials.load()
        if credential is not None:
            if slack.needs_refresh(credential, int(time.time())) and self.authorization.configured:
                try:
                    credential = await self.authorization.refresh(credential)
                except AuthError:
                    pass
            await self.authorization.revoke(credential.access_token)
        self.credentials.delete()
        await self.state.clear()
        return await self.status()

    async def _credential(self) -> tuple[Credential, SlackAccount]:
        credential, account = self.credentials.load(), await self.state.load()
        if credential is None or account is None:
            raise AuthError(self.service, "Slack is not connected.")
        if slack.needs_refresh(credential, int(time.time())):
            try:
                credential = await self.authorization.refresh(credential)
            except AuthError as error:
                self.credentials.delete()
                raise AuthError(self.service, f"{error} Connect Slack again.") from error
            self.credentials.save(credential)
        return credential, account

    async def sync(self) -> SyncResult:
        credential, account = await self._credential()
        token, page = credential.access_token, min(slack.SYNC_COUNT * 3, 100)
        try:
            found = [m for query in slack.queries(account.user_id) for m in await self.api.search(token, query, page)]
            names: dict[str, str] = {}
            messages = [
                await self._message(token, account.user_id, match, names)
                for match in slack.select_recent(found, slack.SYNC_COUNT)
            ]
        except AuthError as error:
            # Revoked or expired: forget the token, keep the topics.
            self.credentials.delete()
            raise AuthError(self.service, f"{error} Connect Slack again.") from error
        return SyncResult(slack.topics(messages), removed=[], complete=True)

    async def _name(self, token: str, user_id: str, names: dict[str, str]) -> str:
        """A user's name, read once per sync."""
        if user_id not in names:
            names[user_id] = await self.api.user_name(token, user_id) or "someone"
        return names[user_id]

    async def _message(self, token: str, me: str, match: Match, names: dict[str, str]) -> DirectMessage:
        outbound = match.user == me
        author = await self._name(token, match.user, names) if match.user else match.username or "someone"
        if not match.is_im:
            counterpart = "Group DM"
        else:
            counterpart = await self._name(token, match.channel_name, names) if outbound else author
        mentioned = {user_id: await self._name(token, user_id, names) for user_id in slack.mention_ids(match.text)}
        return DirectMessage(
            channel_id=match.channel_id,
            ts=match.ts,
            direction=Direction.OUTBOUND if outbound else Direction.INBOUND,
            author=author,
            counterpart=counterpart,
            preview=slack.preview(slack.plain_text(match.text, mentioned)),
            permalink=match.permalink,
            date=slack.ts_to_rfc3339(match.ts),
        )

    async def history(self, topic_key: str) -> list[Message]:
        """The conversation's recent messages, read live, oldest first. Join
        and leave events are left out. Nothing is stored."""
        credential, account = await self._credential()
        token, names = credential.access_token, {}
        try:
            entries = await self.api.history(token, topic_key, slack.HISTORY_COUNT)
            messages = []
            for entry in sorted(entries, key=lambda e: slack.ts_value(e.ts)):
                if entry.subtype in slack.EVENT_SUBTYPES:
                    continue
                author = await self._name(token, entry.user, names) if entry.user else entry.username or "someone"
                mentioned = {u: await self._name(token, u, names) for u in slack.mention_ids(entry.text)}
                messages.append(
                    Message(
                        key=entry.ts,
                        direction=Direction.OUTBOUND if entry.user == account.user_id else Direction.INBOUND,
                        author=author,
                        text=slack.plain_text(entry.text, mentioned).strip(),
                        date=slack.ts_to_rfc3339(entry.ts),
                    )
                )
        except AuthError as error:
            self.credentials.delete()
            raise AuthError(self.service, f"{error} Connect Slack again.") from error
        return messages

    async def reply(self, topic_key: str, body: str) -> None:
        raise Unsupported(self.service, "SilentDesk has read-only access to Slack.")

    async def delete_topic(self, topic_key: str) -> None:
        raise Unsupported(self.service, "SilentDesk has read-only access to Slack.")

    async def delete_item(self, topic_key: str, item_key: str) -> Topic | None:
        raise Unsupported(self.service, "SilentDesk has read-only access to Slack.")
