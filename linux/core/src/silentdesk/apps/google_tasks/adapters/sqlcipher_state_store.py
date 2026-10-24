from __future__ import annotations

from ....contract import Database
from ..domain.state import GoogleState
from ..ports.state_store import StateStore


class SqlcipherStateStore(StateStore):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load(self, service: str) -> GoogleState | None:
        raise NotImplementedError

    async def save(self, service: str, state: GoogleState) -> None:
        raise NotImplementedError

    async def clear(self, service: str) -> None:
        raise NotImplementedError
