"""The desk's topics: each connector topic, kept with SilentDesk's own ID."""

from __future__ import annotations

from dataclasses import dataclass

from ....contract import Item


@dataclass(frozen=True)
class TopicRecord:
    # A UUID, made by SilentDesk.
    id: str
    service: str
    # The connector's key for the topic, such as a Gmail thread ID.
    key: str
    title: str
    # One or more, oldest first.
    items: list[Item]
    # RFC 3339.
    created_at: str
    updated_at: str
    # What the connector said: it can delete the whole topic at once. See
    # `core.topics.deletable` for whether the topic can be deleted at all.
    deletable: bool
    # The user's project for the topic, or None for Default.
    project_id: str | None = None
