"""What the desk app offers the user interfaces: the CLI and the GTK app."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from .connector import Item, Message, ServiceStatus


@dataclass(frozen=True)
class TopicView:
    """One topic, as the queue and the topic screen show it."""

    # SilentDesk's own ID, a UUID.
    id: str
    service: str
    title: str
    # One or more, oldest first.
    items: list[Item]
    # RFC 3339: the newest item's date.
    updated_at: str
    # The whole topic can be deleted: its connector can delete it at once,
    # or every item can be deleted.
    deletable: bool
    # The topic's project, or None for Default.
    project_id: str | None = None


@dataclass(frozen=True)
class Project:
    """A project the user groups topics in. Default is not one."""

    id: str
    name: str


@dataclass(frozen=True)
class TopicQuery:
    """Which topics to list. A topic matches when it has every word of
    `text` and passes every filter. An empty set or None lets every topic
    through; several values in one set match a topic with any of them."""

    # Words, in any case, each found in the title, the service's name, an
    # author or an item key.
    text: str = ""
    # Project IDs, with DEFAULT_PROJECT for topics without a project.
    projects: frozenset[str] = frozenset()
    services: frozenset[str] = frozenset()
    # Authors of any item.
    people: frozenset[str] = frozenset()
    # "others": the newest item is outbound. "me": any other topic.
    waiting_on: frozenset[str] = frozenset()
    # Bounds on `updated_at`, in RFC 3339 with any offset: from included,
    # to excluded.
    updated_from: str | None = None
    updated_to: str | None = None
    deletable: bool | None = None


# In a query, stands for the topics without a project.
DEFAULT_PROJECT = "default"


class Desk(ABC):
    @abstractmethod
    async def topics(self, query: TopicQuery | None = None) -> list[TopicView]:
        """The topics that match `query`, or every topic, newest first."""

    @abstractmethod
    async def projects(self) -> list[Project]:
        """The user's projects, sorted by name, ignoring case."""

    @abstractmethod
    async def add_project(self, name: str) -> Project:
        """Creates a project. Raises `InvalidProjectName` for a name that is
        empty, taken, All or Default, ignoring case."""

    @abstractmethod
    async def rename_project(self, project_id: str, name: str) -> Project:
        """Renames a project, with the rules of `add_project`. Raises
        `UnknownProject` for an ID no project has."""

    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        """Deletes a project; its topics move back to Default."""

    @abstractmethod
    async def move(self, topic_id: str, project_id: str | None) -> None:
        """Moves a topic to a project, or to Default when `project_id` is None."""

    @abstractmethod
    async def services(self) -> list[ServiceStatus]:
        """Every service SilentDesk can connect, connected or not, sorted by name."""

    @abstractmethod
    async def connect(self, service: str, params: Mapping[str, str]) -> ServiceStatus:
        """Connects one service."""

    @abstractmethod
    async def disconnect(self, service: str) -> ServiceStatus:
        """Disconnects one service and drops its topics."""

    @abstractmethod
    async def sync(self, service: str | None = None) -> None:
        """Syncs one service, or every connected service in turn when `service` is None."""

    @abstractmethod
    async def last_synced(self) -> str | None:
        """When topics last changed, in RFC 3339, or None before the first sync."""

    @abstractmethod
    async def history(self, topic_id: str) -> list[Message]:
        """A topic's recent messages with their text, read live from its service."""

    @abstractmethod
    async def reply(self, topic_id: str, body: str) -> None:
        """Replies in a topic, through its service's connector."""

    @abstractmethod
    async def delete(self, topic_id: str) -> None:
        """Deletes a deletable topic in its service, through its connector,
        and drops it: at once if the connector can, otherwise item by item,
        stopping at the first failure with what was deleted kept deleted.
        Raises `Unsupported` for a topic that is not deletable."""

    @abstractmethod
    async def delete_item(self, topic_id: str, item_key: str) -> None:
        """Deletes one deletable item of a topic in its service, and keeps
        the topic as its connector then reports it, or drops it when gone.
        Raises `UnknownItem` for a key the topic does not have, and
        `Unsupported` for an item that is not deletable."""
