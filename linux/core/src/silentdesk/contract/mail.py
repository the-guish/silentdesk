"""What a mail source offers beyond syncing."""

from __future__ import annotations

from abc import abstractmethod

from .source import Source


class Mail(Source):
    @abstractmethod
    async def reply(self, key: str, body: str) -> None:
        """Replies to the message with this key, as the connected account."""

    @abstractmethod
    async def trash(self, key: str) -> None:
        """Moves the message with this key to the trash."""
