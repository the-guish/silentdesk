from __future__ import annotations

from ....contract import Database
from ..domain.state import GmailState
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self) -> GmailState | None:
        raise NotImplementedError

    async def save(self, state: GmailState) -> None:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError
