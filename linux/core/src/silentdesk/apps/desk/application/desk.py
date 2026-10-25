from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping, Sequence

from ....contract import (
    Connector,
    Desk,
    Message,
    ServiceStatus,
    SyncFailed,
    TopicView,
    UnknownItem,
    UnknownService,
    UnknownTopic,
    Unsupported,
)
from ..core import sync as rounds
from ..core import topics
from ..domain.topics import TopicRecord
from ..ports.clock import Clock
from ..ports.topic_store import TopicStore


def _new_id() -> str:
    return str(uuid.uuid4())


class DeskService(Desk):
    def __init__(
        self,
        connectors: Sequence[Connector],
        store: TopicStore,
        clock: Clock,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self.connectors = {connector.service: connector for connector in connectors}
        self.store = store
        self.clock = clock
        self.new_id = new_id
        # One operation per service at a time: a second one waits.
        self.locks = {service: asyncio.Lock() for service in self.connectors}

    async def topics(self) -> list[TopicView]:
        return [
            TopicView(record.id, record.service, record.title, record.items, record.updated_at, record.deletable)
            for record in topics.newest_first(await self.store.topics())
        ]

    async def services(self) -> list[ServiceStatus]:
        return [await self.connectors[service].status() for service in sorted(self.connectors)]

    def _connector(self, service: str) -> Connector:
        if service not in self.connectors:
            raise UnknownService(f"Unknown service {service!r}. Services: {', '.join(sorted(self.connectors))}.")
        return self.connectors[service]

    async def connect(self, service: str, params: Mapping[str, str]) -> ServiceStatus:
        connector = self._connector(service)
        async with self.locks[service]:
            before = await connector.status()
            status = await connector.connect(params)
            if status.account != before.account:
                # Another account: the old one's topics are not this one's.
                await self.store.replace(service, [])
        return status

    async def disconnect(self, service: str) -> ServiceStatus:
        connector = self._connector(service)
        async with self.locks[service]:
            status = await connector.disconnect()
            await self.store.replace(service, [])
        return status

    async def sync(self, service: str | None = None) -> None:
        if service is not None:
            self._connector(service)
            await self._sync_one(service)
            return

        # A round: every connected service in turn. One failure does not stop
        # the others; they are all raised together at the end.
        statuses = [await connector.status() for connector in self.connectors.values()]
        failures: list[tuple[str, Exception]] = []
        for name in rounds.round_order(status.service for status in statuses if status.connected):
            try:
                await self._sync_one(name)
            except Exception as error:  # noqa: BLE001 - reported below, after the other services
                failures.append((name, error))
        if failures:
            raise SyncFailed(failures)

    async def _sync_one(self, service: str) -> None:
        async with self.locks[service]:
            result = await self.connectors[service].sync()
            now = self.clock.now()
            current = [record for record in await self.store.topics() if record.service == service]
            await self.store.replace(service, topics.apply(current, service, result, now, self.new_id))
            await self.store.set_last_synced(now)

    async def last_synced(self) -> str | None:
        return await self.store.last_synced()

    async def _record(self, topic_id: str) -> TopicRecord:
        for record in await self.store.topics():
            if record.id == topic_id:
                return record
        raise UnknownTopic(f"No topic has the ID {topic_id!r}.")

    async def history(self, topic_id: str) -> list[Message]:
        record = await self._record(topic_id)
        async with self.locks[record.service]:
            return await self._connector(record.service).history(record.key)

    async def reply(self, topic_id: str, body: str) -> None:
        if not body.strip():
            raise ValueError("The reply is empty.")
        record = await self._record(topic_id)
        async with self.locks[record.service]:
            await self._connector(record.service).reply(record.key, body)

    async def delete(self, topic_id: str) -> None:
        record = await self._record(topic_id)
        if not record.deletable:
            raise Unsupported(record.service, "This topic cannot be deleted.")
        async with self.locks[record.service]:
            await self._connector(record.service).delete_topic(record.key)
            await self._put(record.service, topic_id, None)

    async def delete_item(self, topic_id: str, item_key: str) -> None:
        record = await self._record(topic_id)
        item = next((item for item in record.items if item.key == item_key), None)
        if item is None:
            raise UnknownItem(f"The topic has no item {item_key!r}.")
        if not item.deletable:
            raise Unsupported(record.service, "This item cannot be deleted.")
        async with self.locks[record.service]:
            await self._connector(record.service).delete_item(record.key, item_key)
            # Read again: a sync may have changed the topic while this waited.
            current = await self._record(topic_id)
            await self._put(record.service, topic_id, topics.without_item(current, item_key))

    async def _put(self, service: str, topic_id: str, record: TopicRecord | None) -> None:
        """Replaces one stored topic with `record`, or drops it for None."""
        others = [r for r in await self.store.topics() if r.service == service and r.id != topic_id]
        await self.store.replace(service, others if record is None else [*others, record])
