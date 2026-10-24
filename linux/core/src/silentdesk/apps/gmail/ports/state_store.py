from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.state import GmailState


class StateStore(ABC):
    """The Gmail app's own tables in the shared database."""

    @abstractmethod
    async def load(self) -> GmailState | None: ...

    @abstractmethod
    async def save(self, state: GmailState) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...
