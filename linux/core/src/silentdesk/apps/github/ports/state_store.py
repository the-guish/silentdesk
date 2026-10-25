from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.github import GitHubAccount


class StateStore(ABC):
    """The GitHub app's own table in the shared database."""

    @abstractmethod
    async def load(self) -> GitHubAccount | None: ...

    @abstractmethod
    async def save(self, account: GitHubAccount) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...
