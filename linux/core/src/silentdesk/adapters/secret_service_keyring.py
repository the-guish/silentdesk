"""The OS credential store on Linux: Secret Service (GNOME Keyring or KWallet)."""

from __future__ import annotations

from ..contract import Keyring


class SecretServiceKeyring(Keyring):
    # The service name every secret is kept under, as in legacy.
    SERVICE = "com.silentdesk.app"

    def get(self, name: str) -> str | None:
        raise NotImplementedError

    def set(self, name: str, value: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError
