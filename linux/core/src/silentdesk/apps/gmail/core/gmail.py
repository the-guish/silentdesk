"""Gmail messages, as far as SilentDesk needs them. Bodies are never kept."""

from __future__ import annotations

from dataclasses import dataclass

from ....contract import Direction


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]
    subject: str
    # The RFC 5322 Message-ID header, needed to reply in the same thread.
    header_id: str
    # RFC 3339, from Gmail's internal date.
    date: str


def direction(message: GmailMessage) -> Direction:
    """Outbound when Gmail labels the message SENT."""
    raise NotImplementedError


def reply(original: GmailMessage, sender: str, body: str) -> bytes:
    """The raw RFC 5322 reply to `original`, in the same thread."""
    raise NotImplementedError
