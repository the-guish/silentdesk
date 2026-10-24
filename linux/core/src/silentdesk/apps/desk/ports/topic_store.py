from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..domain.topics import TopicRecord


class TopicStore(ABC):
    """The desk's own tables in the shared database."""

    @abstractmethod
    async def topics(self) -> list[TopicRecord]: ...

    @abstractmethod
    async def replace(self, service: str, records: Sequence[TopicRecord]) -> None:
        """Replaces every topic of one service, in one transaction."""

    @abstractmethod
    async def last_synced(self) -> str | None: ...

    @abstractmethod
    async def set_last_synced(self, when: str) -> None: ...
