from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from ....contract import Keyring
from ..ports.credentials import Credentials


class KeyringCredentials(Credentials):
    # The keyring entry per service, as in legacy. See spec/storage.md.
    NAMES: ClassVar[Mapping[str, str]] = {"tasks": "google-tasks-refresh-token"}

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    def refresh_token(self, service: str) -> str | None:
        return self.keyring.get(self.NAMES[service])

    def save_refresh_token(self, service: str, token: str) -> None:
        self.keyring.set(self.NAMES[service], token)

    def delete_refresh_token(self, service: str) -> None:
        self.keyring.delete(self.NAMES[service])
