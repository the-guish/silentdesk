"""What the desk app offers the user interfaces: the CLI and the GTK app."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from .connector import Item, ServiceStatus


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


class Desk(ABC):
    @abstractmethod
    async def topics(self) -> list[TopicView]:
        """Every topic, newest first."""

    @abstractmethod
    async def services(self) -> list[ServiceStatus]:
        """Every service SilentDesk can connect, connected or not."""

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
    async def reply(self, topic_id: str, body: str) -> None:
        """Replies to the newest item of a mail topic."""

    @abstractmethod
    async def trash(self, topic_id: str) -> None:
        """Trashes every item of a mail topic and drops the topic."""
