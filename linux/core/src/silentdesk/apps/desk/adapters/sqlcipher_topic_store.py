"""The desk's tables: desk_topics, desk_items, desk_projects and desk_values
(spec/sql/)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ....contract import Database, Direction, Item, Project, StatusCategory, TopicStatus
from ..domain.topics import TopicRecord
from ..ports.topic_store import TopicStore

LAST_SYNCED = "last_synced"


class SqlcipherTopicStore(TopicStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def topics(self) -> list[TopicRecord]:
        with self.database.transaction() as db:
            topics = db.execute(
                "SELECT id, service, key, title, created_at, updated_at, deletable, project_id, status_name,"
                " status_category FROM desk_topics"
            ).fetchall()
            rows = db.execute(
                "SELECT topic_id, key, direction, author, url, date, deletable FROM desk_items"
                " ORDER BY topic_id, position"
            ).fetchall()
        items: dict[str, list[Item]] = defaultdict(list)
        for topic_id, key, direction, author, url, date, deletable in rows:
            items[topic_id].append(
                Item(key, Direction(direction) if direction else None, author, url, date, bool(deletable))
            )
        return [
            TopicRecord(
                id,
                service,
                key,
                title,
                items[id],
                created_at,
                updated_at,
                bool(deletable),
                project_id,
                TopicStatus(status_name, StatusCategory(category) if category else None) if status_name else None,
            )
            for id, service, key, title, created_at, updated_at, deletable, project_id, status_name, category in topics
        ]

    async def replace(self, service: str, records: Sequence[TopicRecord]) -> None:
        with self.database.transaction() as db:
            # Their items go with them (ON DELETE CASCADE).
            db.execute("DELETE FROM desk_topics WHERE service = ?", (service,))
            # A project deleted while the service synced leaves its topics
            # in Default.
            db.executemany(
                "INSERT INTO desk_topics (id, service, key, title, created_at, updated_at, deletable, project_id,"
                " status_name, status_category)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT id FROM desk_projects WHERE id = ?), ?, ?)",
                [
                    (
                        r.id,
                        service,
                        r.key,
                        r.title,
                        r.created_at,
                        r.updated_at,
                        r.deletable,
                        r.project_id,
                        r.status.name if r.status else None,
                        r.status.category if r.status else None,
                    )
                    for r in records
                ],
            )
            db.executemany(
                "INSERT INTO desk_items (topic_id, position, key, direction, author, url, date, deletable)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        r.id,
                        position,
                        i.key,
                        i.direction.value if i.direction else None,
                        i.author,
                        i.url,
                        i.date,
                        i.deletable,
                    )
                    for r in records
                    for position, i in enumerate(r.items)
                ],
            )

    async def projects(self) -> list[Project]:
        with self.database.transaction() as db:
            rows = db.execute("SELECT id, name FROM desk_projects").fetchall()
        return [Project(id, name) for id, name in rows]

    async def save_project(self, project: Project) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO desk_projects (id, name) VALUES (?, ?) ON CONFLICT (id) DO UPDATE SET name = excluded.name",
                (project.id, project.name),
            )

    async def delete_project(self, project_id: str) -> None:
        with self.database.transaction() as db:
            # Its topics go back to Default (ON DELETE SET NULL).
            db.execute("DELETE FROM desk_projects WHERE id = ?", (project_id,))

    async def move(self, topic_id: str, project_id: str | None) -> None:
        with self.database.transaction() as db:
            db.execute("UPDATE desk_topics SET project_id = ? WHERE id = ?", (project_id, topic_id))

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
