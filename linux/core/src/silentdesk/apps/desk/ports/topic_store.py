from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..core.topics import Topic


class TopicStore(ABC):
    """The desk's own tables in the shared database."""

    @abstractmethod
    async def topics(self) -> list[Topic]: ...

    @abstractmethod
    async def replace(self, service: str, topics: Sequence[Topic]) -> None:
        """Replaces every topic of one service, in one transaction."""

    @abstractmethod
    async def last_synced(self) -> str | None: ...

    @abstractmethod
    async def set_last_synced(self, when: str) -> None: ...
