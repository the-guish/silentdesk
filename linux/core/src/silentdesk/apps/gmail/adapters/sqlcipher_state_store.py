"""The Gmail app's table: gmail_state (spec/sql/)."""

from __future__ import annotations

from ....contract import Database
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
