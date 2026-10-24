"""The desk's topics: each connector topic, kept with SilentDesk's own ID."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ....contract import Item, SyncResult


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


def apply(
    records: Sequence[TopicRecord], service: str, result: SyncResult, now: str, new_id: Callable[[], str]
) -> list[TopicRecord]:
    """The records after one service's sync: new topics get records, changed
    topics update theirs and keep their ID, and gone topics lose theirs."""
    raise NotImplementedError


def newest_first(records: Sequence[TopicRecord]) -> list[TopicRecord]:
    raise NotImplementedError
