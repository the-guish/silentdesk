from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.jira import JiraAccount


class StateStore(ABC):
    """The Jira app's own table in the shared database."""

    @abstractmethod
    async def load(self) -> JiraAccount | None: ...

    @abstractmethod
    async def save(self, account: JiraAccount) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...
