from __future__ import annotations

import json

from ....contract import Keyring
from ..domain.slack import Credential
from ..ports.credentials import Credentials


class KeyringCredentials(Credentials):
    # The keyring entry, as in legacy: {"access_token", "refresh_token", "expires_at"}.
    NAME = "slack-credential"

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    def load(self) -> Credential | None:
        stored = self.keyring.get(self.NAME)
        try:
            value = json.loads(stored) if stored else None
        except ValueError:
            return None
        if not isinstance(value, dict) or not isinstance(value.get("access_token"), str):
            return None
        refresh, expires = value.get("refresh_token"), value.get("expires_at")
        return Credential(
            value["access_token"],
            refresh if isinstance(refresh, str) else None,
            expires if isinstance(expires, int) else None,
        )

    def save(self, credential: Credential) -> None:
        value = {
            "access_token": credential.access_token,
            "refresh_token": credential.refresh_token,
            "expires_at": credential.expires_at,
        }
        self.keyring.set(self.NAME, json.dumps(value, separators=(",", ":"), ensure_ascii=False))

    def delete(self) -> None:
        self.keyring.delete(self.NAME)
