from __future__ import annotations

from ....infra.keyring import Keyring
from ..ports.credentials import Credentials


class KeyringCredentials(Credentials):
    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    def refresh_token(self, service: str) -> str | None:
        raise NotImplementedError

    def save_refresh_token(self, service: str, token: str) -> None:
        raise NotImplementedError

    def delete_refresh_token(self, service: str) -> None:
        raise NotImplementedError
