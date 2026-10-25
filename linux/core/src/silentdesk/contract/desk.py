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


@dataclass(frozen=True)
class TopicQuery:
    """Which topics to list. A topic matches when it has every word of
    `text` and passes every filter. An empty set or None lets every topic
    through; several values in one set match a topic with any of them."""

    # Words, in any case, each found in the title, the service's name, an
    # author or an item key.
    text: str = ""
    services: frozenset[str] = frozenset()
    # Authors of any item.
    people: frozenset[str] = frozenset()
    # "others": the newest item is outbound. "me": any other topic.
    waiting_on: frozenset[str] = frozenset()
    # RFC 3339 bounds on `updated_at`: from included, to excluded.
    updated_from: str | None = None
    updated_to: str | None = None
    deletable: bool | None = None


class Desk(ABC):
    @abstractmethod
    async def topics(self, query: TopicQuery | None = None) -> list[TopicView]:
        """The topics that match `query`, or every topic, newest first."""

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
