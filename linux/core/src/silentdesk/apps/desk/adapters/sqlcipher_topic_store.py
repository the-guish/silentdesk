from __future__ import annotations

from collections.abc import Sequence

from ....infra.database import Database
from ..core.topics import Topic
from ..ports.topic_store import TopicStore


class SqlcipherTopicStore(TopicStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def topics(self) -> list[Topic]:
        raise NotImplementedError

    async def replace(self, service: str, topics: Sequence[Topic]) -> None:
        raise NotImplementedError

    async def last_synced(self) -> str | None:
        raise NotImplementedError

    async def set_last_synced(self, when: str) -> None:
        raise NotImplementedError
