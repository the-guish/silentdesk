"""The one database file every app keeps its own tables in. See spec/storage.md."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Database(ABC):
    @abstractmethod
    def connect(self) -> Any:
        """An open DB-API 2.0 connection to the encrypted database, created
        with its key on first run."""

    @abstractmethod
    def migrate(self) -> None:
        """Runs the migrations in spec/sql/ that have not run yet."""
