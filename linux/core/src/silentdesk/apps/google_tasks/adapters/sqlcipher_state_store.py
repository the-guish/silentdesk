"""The Google Tasks app's table: google_tasks_state (spec/sql/)."""

from __future__ import annotations

from ....contract import Database
from ..domain.state import GoogleState
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self, service: str) -> GoogleState | None:
        with self.database.transaction() as db:
            row = db.execute("SELECT email FROM google_tasks_state WHERE service = ?", (service,)).fetchone()
        return GoogleState(email=row[0]) if row else None

    async def save(self, service: str, state: GoogleState) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO google_tasks_state (service, email) VALUES (?, ?)"
                " ON CONFLICT (service) DO UPDATE SET email = excluded.email",
                (service, state.email),
            )

    async def clear(self, service: str) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM google_tasks_state WHERE service = ?", (service,))
