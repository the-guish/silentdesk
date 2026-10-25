from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.slack import SlackAccount


class StateStore(ABC):
    """The Slack app's own table in the shared database."""

    @abstractmethod
    async def load(self) -> SlackAccount | None: ...

    @abstractmethod
    async def save(self, account: SlackAccount) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...
