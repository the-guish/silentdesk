from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.jira import Credential


class Credentials(ABC):
    """The email and token, kept in the OS credential store."""

    @abstractmethod
    def load(self) -> Credential | None: ...

    @abstractmethod
    def save(self, credential: Credential) -> None: ...

    @abstractmethod
    def delete(self) -> None: ...
