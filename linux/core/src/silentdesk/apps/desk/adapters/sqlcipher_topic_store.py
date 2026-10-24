"""The desk's tables: desk_topics, desk_items and desk_values (spec/sql/)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ....contract import Database, Direction, Item
from ..domain.topics import TopicRecord
from ..ports.topic_store import TopicStore

LAST_SYNCED = "last_synced"


class SqlcipherTopicStore(TopicStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def topics(self) -> list[TopicRecord]:
        with self.database.transaction() as db:
            topics = db.execute("SELECT id, service, key, title, created_at, updated_at FROM desk_topics").fetchall()
            rows = db.execute(
                "SELECT topic_id, key, direction, author, url, date FROM desk_items ORDER BY topic_id, position"
            ).fetchall()
        items: dict[str, list[Item]] = defaultdict(list)
        for topic_id, key, direction, author, url, date in rows:
            items[topic_id].append(Item(key, Direction(direction) if direction else None, author, url, date))
        return [
            TopicRecord(id, service, key, title, items[id], created_at, updated_at)
            for id, service, key, title, created_at, updated_at in topics
        ]

    async def replace(self, service: str, records: Sequence[TopicRecord]) -> None:
        with self.database.transaction() as db:
            # Their items go with them (ON DELETE CASCADE).
            db.execute("DELETE FROM desk_topics WHERE service = ?", (service,))
            db.executemany(
                "INSERT INTO desk_topics (id, service, key, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                [(r.id, service, r.key, r.title, r.created_at, r.updated_at) for r in records],
            )
            db.executemany(
                "INSERT INTO desk_items (topic_id, position, key, direction, author, url, date)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (r.id, position, i.key, i.direction.value if i.direction else None, i.author, i.url, i.date)
                    for r in records
                    for position, i in enumerate(r.items)
                ],
            )

    async def last_synced(self) -> str | None:
        with self.database.transaction() as db:
            row = db.execute("SELECT value FROM desk_values WHERE name = ?", (LAST_SYNCED,)).fetchone()
        return row[0] if row else None

    async def set_last_synced(self, when: str) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO desk_values (name, value) VALUES (?, ?) ON CONFLICT (name) DO UPDATE SET value = excluded.value",
                (LAST_SYNCED, when),
            )
