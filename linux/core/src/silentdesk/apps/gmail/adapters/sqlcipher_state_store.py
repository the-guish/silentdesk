"""The Gmail app's tables: gmail_state and gmail_messages (spec/sql/)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ....contract import Database, Direction
from ..domain.gmail import GmailMessage
from ..domain.state import GmailState
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self) -> GmailState | None:
        with self.database.transaction() as db:
            row = db.execute("SELECT email, history_id FROM gmail_state WHERE id = 1").fetchone()
        return GmailState(*row) if row else None

    async def save(self, state: GmailState) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO gmail_state (id, email, history_id) VALUES (1, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET email = excluded.email, history_id = excluded.history_id",
                (state.email, state.history_id),
            )

    async def clear(self) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM gmail_state")
            db.execute("DELETE FROM gmail_messages")

    async def known_ids(self) -> set[str]:
        with self.database.transaction() as db:
            return {row[0] for row in db.execute("SELECT message_id FROM gmail_messages")}

    async def add_messages(self, messages: Sequence[GmailMessage]) -> None:
        with self.database.transaction() as db:
            db.executemany(
                "INSERT OR IGNORE INTO gmail_messages (message_id, thread_id, direction, sender, subject, date)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [(m.message_id, m.thread_id, m.direction.value, m.sender, m.subject, m.date) for m in messages],
            )

    async def threads(self, thread_ids: Sequence[str] | None = None) -> dict[str, list[GmailMessage]]:
        query = "SELECT message_id, thread_id, direction, sender, subject, date FROM gmail_messages"
        with self.database.transaction() as db:
            if thread_ids is None:
                rows = db.execute(query).fetchall()
            else:
                marks = ",".join("?" * len(thread_ids))
                rows = (
                    db.execute(f"{query} WHERE thread_id IN ({marks})", list(thread_ids)).fetchall()
                    if thread_ids
                    else []
                )
        threads: dict[str, list[GmailMessage]] = defaultdict(list)
        for message_id, thread_id, direction, sender, subject, date in rows:
            threads[thread_id].append(GmailMessage(message_id, thread_id, Direction(direction), sender, subject, date))
        return dict(threads)

    async def remove_thread(self, thread_id: str) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM gmail_messages WHERE thread_id = ?", (thread_id,))

    async def remove_message(self, message_id: str) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM gmail_messages WHERE message_id = ?", (message_id,))
