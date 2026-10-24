"""What a mail connector offers beyond syncing."""

from __future__ import annotations

from abc import abstractmethod

from .connector import Connector


class Mail(Connector):
    @abstractmethod
    async def reply(self, key: str, body: str) -> None:
        """Replies to the item with this key, as the connected account."""

    @abstractmethod
    async def trash(self, key: str) -> None:
        """Moves the item with this key to the trash."""
