from __future__ import annotations

from abc import ABC, abstractmethod


class Credentials(ABC):
    """Gmail's refresh token, kept in the OS credential store."""

    @abstractmethod
    def refresh_token(self) -> str | None: ...

    @abstractmethod
    def save_refresh_token(self, token: str) -> None: ...

    @abstractmethod
    def delete_refresh_token(self) -> None: ...
