"""The SQLCipher database. See spec/storage.md."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlcipher3

from ..contract import Database, Keyring, StorageError

# The shared migrations: silentdesk/sql links to spec/sql.
MIGRATIONS = Path(__file__).resolve().parent.parent / "sql"


class SqlcipherDatabase(Database):
    # The keyring entry holding the database key.
    KEY_NAME = "database-key"

    def __init__(self, path: Path, keyring: Keyring, migrations: Path = MIGRATIONS) -> None:
        self.path = path
        self.keyring = keyring
        self.migrations = migrations
        self._connection: Any = None

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = self._open()
        connection.execute("BEGIN")
        try:
            yield connection
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    def _open(self) -> Any:
        if self._connection is None:
            connection = self._connect()
            self._migrate(connection)
            self._connection = connection
        return self._connection

    def _connect(self) -> Any:
        key = self.keyring.get(self.KEY_NAME)
        if key is None:
            if self.path.exists():
                raise StorageError(f"The database {self.path} cannot be opened: its key is missing from the keyring.")
            key = secrets.token_hex(32)
            self.keyring.set(self.KEY_NAME, key)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Created readable by the user only, before SQLCipher writes to it.
        os.close(os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600))

        # Autocommit, so transaction() and _migrate() decide where transactions start.
        connection = sqlcipher3.connect(self.path, isolation_level=None)
        connection.execute("PRAGMA cipher_log_level = NONE")
        connection.execute(f"PRAGMA key = \"x'{key}'\"")
        try:
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlcipher3.DatabaseError as error:
            connection.close()
            raise StorageError(f"The database {self.path} cannot be opened: {error}.") from error
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self, connection: Any) -> None:
        """Runs the migrations above the database's user_version, in one transaction."""
        (current,) = connection.execute("PRAGMA user_version").fetchone()
        pending = sorted(
            (int(path.name.split("_", 1)[0]), path)
            for path in self.migrations.glob("*.sql")
            if int(path.name.split("_", 1)[0]) > current
        )
        if not pending:
            return
        script = "".join(path.read_text() + "\n" for _, path in pending)
        try:
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {pending[-1][0]};\nCOMMIT;")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
