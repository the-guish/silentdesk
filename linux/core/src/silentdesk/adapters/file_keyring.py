"""A keyring in a plain JSON file, for tests only: it stores secrets
unencrypted. Used when SILENTDESK_TEST_KEYRING is set; see spec/cli.md."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..contract import Keyring


class FileKeyring(Keyring):
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, name: str) -> str | None:
        return self._read().get(name)

    def set(self, name: str, value: str) -> None:
        self._write({**self._read(), name: value})

    def delete(self, name: str) -> None:
        entries = self._read()
        if entries.pop(name, None) is not None:
            self._write(entries)

    def _read(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def _write(self, entries: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Readable by the user only, like the real credential store.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as file:
            json.dump(entries, file, indent=2, sort_keys=True)
