from __future__ import annotations

from abc import ABC, abstractmethod


class Credentials(ABC):
    """The personal access token, kept in the OS credential store."""

    @abstractmethod
    def token(self) -> str | None: ...

    @abstractmethod
    def save_token(self, token: str) -> None: ...

    @abstractmethod
    def delete_token(self) -> None: ...
