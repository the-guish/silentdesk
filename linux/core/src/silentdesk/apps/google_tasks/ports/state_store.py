from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.state import GoogleState


class StateStore(ABC):
    """The Google Tasks app's own tables in the shared database."""

    @abstractmethod
    async def load(self, service: str) -> GoogleState | None: ...

    @abstractmethod
    async def save(self, service: str, state: GoogleState) -> None: ...

    @abstractmethod
    async def clear(self, service: str) -> None: ...
