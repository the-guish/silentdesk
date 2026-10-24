"""The OS credential store: Secret Service (GNOME Keyring or KWallet)."""

from __future__ import annotations


class Keyring:
    # The service name every secret is kept under, as in legacy.
    SERVICE = "com.silentdesk.app"

    def get(self, name: str) -> str | None:
        raise NotImplementedError

    def set(self, name: str, value: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError
