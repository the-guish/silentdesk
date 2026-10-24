"""Rules about Gmail messages."""

from __future__ import annotations

from ....contract import Direction
from ..domain.gmail import GmailMessage


def direction(message: GmailMessage) -> Direction:
    """Outbound when Gmail labels the message SENT."""
    raise NotImplementedError


def reply(original: GmailMessage, sender: str, body: str) -> bytes:
    """The raw RFC 5322 reply to `original`, in the same thread."""
    raise NotImplementedError
