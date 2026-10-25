from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..domain.gmail import GmailMessage
from ..domain.state import GmailState


class StateStore(ABC):
    """The Gmail app's own tables in the shared database: the account, and
    the headers of every synced message."""

    @abstractmethod
    async def load(self) -> GmailState | None: ...

    @abstractmethod
    async def save(self, state: GmailState) -> None: ...

    @abstractmethod
    async def clear(self) -> None:
        """Forgets the account and every message."""

    @abstractmethod
    async def known_ids(self) -> set[str]: ...

    @abstractmethod
    async def add_messages(self, messages: Sequence[GmailMessage]) -> None: ...

    @abstractmethod
    async def threads(self, thread_ids: Sequence[str] | None = None) -> dict[str, list[GmailMessage]]:
        """Messages by thread: of the given threads, or of every thread."""

    @abstractmethod
    async def remove_thread(self, thread_id: str) -> None: ...

    @abstractmethod
    async def remove_message(self, message_id: str) -> None: ...
