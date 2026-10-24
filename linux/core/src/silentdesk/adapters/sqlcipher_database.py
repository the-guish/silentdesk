"""The SQLCipher database. See spec/storage.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contract import Database, Keyring


class SqlcipherDatabase(Database):
    # The keyring entry holding the database key.
    KEY_NAME = "database-key"

    def __init__(self, path: Path, keyring: Keyring) -> None:
        self.path = path
        self.keyring = keyring

    def connect(self) -> Any:
        """A sqlcipher3 connection. Refuses to open an existing file whose key is missing."""
        raise NotImplementedError

    def migrate(self) -> None:
        raise NotImplementedError
