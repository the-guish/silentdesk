"""The Jira app's table: jira_state (spec/sql/)."""

from __future__ import annotations

from ....contract import Database
from ..domain.jira import Endpoint, Flavor, JiraAccount
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self) -> JiraAccount | None:
        with self.database.transaction() as db:
            row = db.execute(
                "SELECT user_id, user_name, site, api_base, flavor FROM jira_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        user_id, user_name, site, api_base, flavor = row
        return JiraAccount(user_id, user_name, Endpoint(site, api_base, Flavor(flavor)))

    async def save(self, account: JiraAccount) -> None:
        endpoint = account.endpoint
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO jira_state (id, user_id, user_name, site, api_base, flavor) VALUES (1, ?, ?, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET user_id = excluded.user_id, user_name = excluded.user_name,"
                " site = excluded.site, api_base = excluded.api_base, flavor = excluded.flavor",
                (account.user_id, account.user_name, endpoint.site, endpoint.api_base, endpoint.flavor.value),
            )

    async def clear(self) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM jira_state")
