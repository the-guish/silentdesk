from __future__ import annotations

import json

from ....contract import Keyring
from ..domain.jira import Credential
from ..ports.credentials import Credentials


class KeyringCredentials(Credentials):
    # The keyring entry, as in legacy: {"email": ..., "token": ...}. See spec/storage.md.
    NAME = "jira-credential"

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring

    def load(self) -> Credential | None:
        stored = self.keyring.get(self.NAME)
        try:
            value = json.loads(stored) if stored else None
        except ValueError:
            return None
        if not isinstance(value, dict) or not isinstance(value.get("token"), str):
            return None
        email = value.get("email")
        return Credential(email if isinstance(email, str) else None, value["token"])

    def save(self, credential: Credential) -> None:
        value = {"email": credential.email, "token": credential.token}
        self.keyring.set(self.NAME, json.dumps(value, separators=(",", ":"), ensure_ascii=False))

    def delete(self) -> None:
        self.keyring.delete(self.NAME)
