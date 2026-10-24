"""What every source app offers for each service it connects: Gmail, Google
Tasks, and later Slack, Jira and GitHub."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass


class Direction(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass(frozen=True)
class ServiceStatus:
    """What the user needs to know about one service."""

    service: str
    # The app has the client ID or settings it needs to sign in.
    configured: bool
    connected: bool
    # The account as shown to the user, such as an email address.
    account: str | None


@dataclass(frozen=True)
class Item:
    """One thing in a corporate system that can become a topic: an email, a
    task, a message, an issue or a pull request. Only what the queue shows."""

    service: str
    # Stable within the service, such as a Gmail message ID.
    key: str
    title: str
    direction: Direction | None
    # Opens the item in its own system.
    url: str | None
    # RFC 3339.
    updated_at: str


@dataclass(frozen=True)
class SyncResult:
    """What one sync found. When `complete` is true, `items` is everything the
    service has now, and any item not in it is gone."""

    items: list[Item]
    # Keys of items that are gone from the service.
    removed: list[str]
    complete: bool


class Source(ABC):
    """One connected service."""

    @property
    @abstractmethod
    def service(self) -> str:
        """The service's name, such as "gmail"."""

    @abstractmethod
    async def status(self) -> ServiceStatus:
        """Whether the service is configured and connected, and to which account."""

    @abstractmethod
    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        """Signs in, with the user's form fields or through the browser."""

    @abstractmethod
    async def disconnect(self) -> ServiceStatus:
        """Signs out and forgets everything kept for this service."""

    @abstractmethod
    async def sync(self) -> SyncResult:
        """Reads what changed since the last sync."""
