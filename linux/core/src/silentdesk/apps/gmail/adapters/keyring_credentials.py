from __future__ import annotations

from ....contract import Keyring
from ..ports.credentials import Credentials


class KeyringCredentials(Credentials):
    # The keyring entry, as in legacy.
    NAME = "gmail-refresh-token"

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    def refresh_token(self) -> str | None:
        raise NotImplementedError

    def save_refresh_token(self, token: str) -> None:
        raise NotImplementedError

    def delete_refresh_token(self) -> None:
        raise NotImplementedError
