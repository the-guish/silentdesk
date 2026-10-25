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
    # The whole topic can be deleted: its connector said so, or every item
    # can be.
    deletable: bool
