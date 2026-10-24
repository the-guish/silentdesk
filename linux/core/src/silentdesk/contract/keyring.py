"""The OS credential store, where secrets and the database key live."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Keyring(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None: ...

    @abstractmethod
    def set(self, name: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, name: str) -> None: ...
