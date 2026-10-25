from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.gmail import GmailMessage, Original


@dataclass(frozen=True)
class Profile:
    email: str
    # Marks the mailbox's current state; changes after it can be listed.
    history_id: str


class GmailApi(ABC):
    """Gmail's REST API, headers only. Every call takes a current access token."""

    @abstractmethod
    async def profile(self, token: str) -> Profile: ...

    @abstractmethod
    async def inbox_ids(self, token: str) -> list[str]:
        """Every message in the Inbox, newest first."""

    @abstractmethod
    async def inbox_changes(self, token: str, history_id: str) -> tuple[list[str], str] | None:
        """Messages that entered the Inbox since `history_id`, and where the
        next sync starts; None when Gmail no longer keeps history that old."""

    @abstractmethod
    async def messages(self, token: str, ids: list[str], progress: Callable[[int], None]) -> list[GmailMessage]:
        """The headers of each message, read at the pace Google allows, in
        the order of `ids`. Drafts, chats and messages deleted meanwhile are
        left out. `progress` gets how many were read so far."""

    @abstractmethod
    async def original(self, token: str, message_id: str) -> Original:
        """The headers a reply to the message needs."""

    @abstractmethod
    async def send(self, token: str, thread_id: str, message: str) -> None:
        """Sends an RFC 5322 message in the thread."""

    @abstractmethod
    async def trash_thread(self, token: str, thread_id: str) -> None:
        """Moves the thread to the trash, where Gmail deletes it after 30 days."""

    @abstractmethod
    async def trash_message(self, token: str, message_id: str) -> None:
        """Moves one message to the trash, where Gmail deletes it after 30 days."""
