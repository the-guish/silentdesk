"""Rules about topics: how a sync changes them, and their order."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ....contract import SyncResult, Topic
from ..domain.topics import TopicRecord


def apply(
    records: Sequence[TopicRecord], service: str, result: SyncResult, now: str, new_id: Callable[[], str]
) -> list[TopicRecord]:
    """One service's records after its sync: new topics get records, changed
    topics update theirs and keep their ID, and gone topics lose theirs.
    `records` holds only that service's records."""
    old = {record.key: record for record in records}
    if result.complete:
        kept: dict[str, TopicRecord] = {}
    else:
        removed = set(result.removed)
        kept = {key: record for key, record in old.items() if key not in removed}
    for topic in result.topics:
        kept[topic.key] = _record(topic, service, old.get(topic.key), now, new_id)
    return list(kept.values())


def _record(topic: Topic, service: str, old: TopicRecord | None, now: str, new_id: Callable[[], str]) -> TopicRecord:
    return TopicRecord(
        id=old.id if old else new_id(),
        service=service,
        key=topic.key,
        title=topic.title,
        items=list(topic.items),
        created_at=old.created_at if old else now,
        # RFC 3339 times in UTC sort as text.
        updated_at=max((item.date for item in topic.items), default=now),
    )


def newest_first(records: Sequence[TopicRecord]) -> list[TopicRecord]:
    return sorted(records, key=lambda record: (record.updated_at, record.id), reverse=True)
