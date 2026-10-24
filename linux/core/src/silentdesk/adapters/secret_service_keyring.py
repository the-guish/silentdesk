"""The OS credential store on Linux: Secret Service (GNOME Keyring or KWallet)."""

from __future__ import annotations

import keyring
from keyring.errors import PasswordDeleteError

from ..contract import Keyring


class SecretServiceKeyring(Keyring):
    # The service name every secret is kept under, as in legacy.
    SERVICE = "com.silentdesk.app"

    def get(self, name: str) -> str | None:
        return keyring.get_password(self.SERVICE, name)

    def set(self, name: str, value: str) -> None:
        keyring.set_password(self.SERVICE, name, value)

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self.SERVICE, name)
        except PasswordDeleteError:
            # Already gone.
            pass
