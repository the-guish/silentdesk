from __future__ import annotations

from collections.abc import Mapping, Sequence

from ....contract import Connector, Desk, ServiceStatus, TopicView
from ..ports.clock import Clock
from ..ports.topic_store import TopicStore


class DeskService(Desk):
    def __init__(self, connectors: Sequence[Connector], store: TopicStore, clock: Clock) -> None:
        self.connectors = {connector.service: connector for connector in connectors}
        self.store = store
        self.clock = clock

    async def topics(self) -> list[TopicView]:
        raise NotImplementedError

    async def services(self) -> list[ServiceStatus]:
        raise NotImplementedError

    async def connect(self, service: str, params: Mapping[str, str]) -> ServiceStatus:
        raise NotImplementedError

    async def disconnect(self, service: str) -> ServiceStatus:
        raise NotImplementedError

    async def sync(self, service: str | None = None) -> None:
        raise NotImplementedError

    async def last_synced(self) -> str | None:
        raise NotImplementedError

    async def reply(self, topic_id: str, body: str) -> None:
        raise NotImplementedError

    async def trash(self, topic_id: str) -> None:
        raise NotImplementedError
