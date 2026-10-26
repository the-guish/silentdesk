"""The one database file every app keeps its own tables in. See docs/specs/storage.md."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Any


class StorageError(Exception):
    """The database cannot be opened, such as when its key is missing."""


class Database(ABC):
    @abstractmethod
    def transaction(self) -> AbstractContextManager[Any]:
        """A DB-API 2.0 connection inside one transaction: committed when the
        block ends, rolled back if it raises. Opens and migrates the database
        on first use, and raises StorageError if it cannot."""
