"""The SQLCipher database file that every app keeps its tables in. See
spec/storage.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .keyring import Keyring


class Database:
    # The keyring entry holding the database key.
    KEY_NAME = "database-key"

    def __init__(self, path: Path, keyring: Keyring) -> None:
        self.path = path
        self.keyring = keyring

    def connect(self) -> Any:
        """Opens the database with its key, creating both on first run, and
        returns a sqlcipher3 connection. Refuses to open an existing file
        whose key is missing."""
        raise NotImplementedError

    def migrate(self) -> None:
        """Runs the migrations in spec/sql/ that have not run yet."""
        raise NotImplementedError
