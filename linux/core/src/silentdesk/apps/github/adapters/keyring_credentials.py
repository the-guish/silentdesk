from __future__ import annotations

from ....contract import Keyring
from ..ports.credentials import Credentials


class KeyringCredentials(Credentials):
    # The keyring entry, as in legacy. See spec/storage.md.
    NAME = "github-token"

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    def token(self) -> str | None:
        return self.keyring.get(self.NAME)

    def save_token(self, token: str) -> None:
        self.keyring.set(self.NAME, token)

    def delete_token(self) -> None:
        self.keyring.delete(self.NAME)
