from __future__ import annotations

from abc import ABC, abstractmethod


class Credentials(ABC):
    """Refresh tokens, one per service, kept in the OS credential store."""

    @abstractmethod
    def refresh_token(self, service: str) -> str | None: ...

    @abstractmethod
    def save_refresh_token(self, service: str, token: str) -> None: ...

    @abstractmethod
    def delete_refresh_token(self, service: str) -> None: ...
