"""The GitHub app's table: github_state (spec/sql/)."""

from __future__ import annotations

from ....contract import Database
from ..domain.github import Endpoint, GitHubAccount
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self) -> GitHubAccount | None:
        with self.database.transaction() as db:
            row = db.execute("SELECT login, name, api_base, web_base FROM github_state WHERE id = 1").fetchone()
        if row is None:
            return None
        login, name, api_base, web_base = row
        return GitHubAccount(login, name, Endpoint(api_base, web_base))

    async def save(self, account: GitHubAccount) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO github_state (id, login, name, api_base, web_base) VALUES (1, ?, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET login = excluded.login, name = excluded.name,"
                " api_base = excluded.api_base, web_base = excluded.web_base",
                (account.login, account.name, account.endpoint.api_base, account.endpoint.web_base),
            )

    async def clear(self) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM github_state")
