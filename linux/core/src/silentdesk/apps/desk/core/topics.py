"""Rules about topics: how a sync changes them, and their order."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ....contract import SyncResult
from ..domain.topics import TopicRecord


def apply(
    records: Sequence[TopicRecord], service: str, result: SyncResult, now: str, new_id: Callable[[], str]
) -> list[TopicRecord]:
    """The records after one service's sync: new topics get records, changed
    topics update theirs and keep their ID, and gone topics lose theirs."""
    raise NotImplementedError


def newest_first(records: Sequence[TopicRecord]) -> list[TopicRecord]:
    raise NotImplementedError
