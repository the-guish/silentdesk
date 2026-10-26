from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ....contract import Project
from ..domain.topics import TopicRecord


class TopicStore(ABC):
    """The desk's own tables in the shared database."""

    @abstractmethod
    async def topics(self) -> list[TopicRecord]: ...

    @abstractmethod
    async def replace(self, service: str, records: Sequence[TopicRecord]) -> None:
        """Replaces every topic of one service, in one transaction."""

    @abstractmethod
    async def projects(self) -> list[Project]: ...

    @abstractmethod
    async def save_project(self, project: Project) -> None:
        """Adds a project, or renames the one with its ID."""

    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        """Deletes a project; its topics move back to Default."""

    @abstractmethod
    async def move(self, topic_id: str, project_id: str | None) -> None:
        """Sets a topic's project, None for Default."""

    @abstractmethod
    async def last_synced(self) -> str | None: ...

    @abstractmethod
    async def set_last_synced(self, when: str) -> None: ...
