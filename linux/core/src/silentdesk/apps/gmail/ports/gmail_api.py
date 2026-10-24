from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.gmail import GmailMessage


@dataclass(frozen=True)
class InboxPage:
    message_ids: list[str]
    next_page_token: str | None
    # The mailbox's history ID when the page was read.
    history_id: str


@dataclass(frozen=True)
class Changes:
    added: list[str]
    removed: list[str]
    history_id: str


class GmailApi(ABC):
    """Gmail's REST API. Every call takes a current access token."""

    @abstractmethod
    async def account_email(self, token: str) -> str: ...

    @abstractmethod
    async def inbox(self, token: str, page_token: str | None) -> InboxPage: ...

    @abstractmethod
    async def message(self, token: str, message_id: str) -> GmailMessage: ...

    @abstractmethod
    async def changes(self, token: str, history_id: str) -> Changes:
        """Inbox changes since `history_id`."""

    @abstractmethod
    async def send(self, token: str, raw: bytes, thread_id: str) -> None: ...

    @abstractmethod
    async def trash(self, token: str, message_id: str) -> None: ...
