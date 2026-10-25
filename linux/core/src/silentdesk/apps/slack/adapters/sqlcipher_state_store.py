"""The Slack app's table: slack_state (spec/sql/)."""

from __future__ import annotations

from ....contract import Database
from ..domain.slack import SlackAccount
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self) -> SlackAccount | None:
        with self.database.transaction() as db:
            row = db.execute("SELECT user_id, user_name, team_id, team_name FROM slack_state WHERE id = 1").fetchone()
        return SlackAccount(*row) if row else None

    async def save(self, account: SlackAccount) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO slack_state (id, user_id, user_name, team_id, team_name) VALUES (1, ?, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET user_id = excluded.user_id, user_name = excluded.user_name,"
                " team_id = excluded.team_id, team_name = excluded.team_name",
                (account.user_id, account.user_name, account.team_id, account.team_name),
            )

    async def clear(self) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM slack_state")
