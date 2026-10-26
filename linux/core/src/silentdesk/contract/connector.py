"""What every connector app offers for each service it connects: Gmail,
Google Tasks, and later Slack, Jira and GitHub. A connector both reads from
its service and sends to it."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass


class Direction(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class StatusCategory(enum.StrEnum):
    """Where a status stands, the same for every service."""

    NEW = "new"
    IN_PROGRESS = "inProgress"
    DONE = "done"


@dataclass(frozen=True)
class TopicStatus:
    """The status a service gives a topic, such as a Jira issue's. See
    docs/specs/topic-status.md."""

    # As the service writes it, such as "Code Review".
    name: str
    category: StatusCategory | None


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
    """One message in a topic, such as an email or a chat message. A task,
    an issue or a pull request is a topic with one item. Only what the queue
    shows: bodies are never kept."""

    # Stable within the service, such as a Gmail message ID.
    key: str
    direction: Direction | None
    # Who wrote it, as shown to the user.
    author: str | None
    # Opens the item in its own system.
    url: str | None
    # RFC 3339.
    date: str
    # The user can delete it in its service now, as the connector judges it
    # at sync time. The service has the last word: its refusal is an error.
    deletable: bool


@dataclass(frozen=True)
class Topic:
    """A unit of work, as the connector groups it: an email thread, a chat
    conversation, a task, an issue or a pull request."""

    # Stable within the service, such as a Gmail thread ID.
    key: str
    title: str
    # One or more, oldest first.
    items: list[Item]
    # The service can delete the whole topic now, in one operation, such as
    # trashing a Gmail thread. When this is false but every item is
    # deletable, the desk deletes the topic item by item instead.
    deletable: bool
    # None for a service that gives its topics no status.
    status: TopicStatus | None = None


@dataclass(frozen=True)
class Message:
    """One message of a topic with its text, read live for the topic screen.
    Shown, never stored."""

    key: str
    direction: Direction | None
    author: str | None
    text: str
    # RFC 3339.
    date: str


@dataclass(frozen=True)
class SyncResult:
    """What one sync found. When `complete` is true, `topics` is everything
    the service has now, and any topic not in it is gone."""

    # New or changed topics, each with all of its items.
    topics: list[Topic]
    # Keys of topics that are gone from the service.
    removed: list[str]
    complete: bool


class Connector(ABC):
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

    @abstractmethod
    async def reply(self, topic_key: str, body: str) -> None:
        """Replies in the topic with this key, as the connected account.
        Raises `Unsupported` if the service has no replies."""

    @abstractmethod
    async def history(self, topic_key: str) -> list[Message]:
        """The topic's recent messages with their text, oldest first, read
        live from the service. Raises `Unsupported` if the service has none."""

    @abstractmethod
    async def delete_topic(self, topic_key: str) -> None:
        """Deletes the topic with this key in its service, such as moving an
        email thread to the trash. The desk calls it only for a topic marked
        deletable; `Unsupported` is a safety net for any other. Later syncs
        must not send the topic again unless the service has it again."""

    @abstractmethod
    async def delete_item(self, topic_key: str, item_key: str) -> Topic | None:
        """Deletes one item of the topic in its service, such as moving one
        email to the trash, and returns the topic as it is now, or None when
        it is gone: its title or deletability may change with its items. The
        desk calls it only for an item marked deletable; `Unsupported` is a
        safety net for any other. Later syncs must not send the item again
        unless the service has it again."""
