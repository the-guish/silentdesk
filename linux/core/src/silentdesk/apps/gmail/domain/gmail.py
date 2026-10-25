"""Gmail messages, as far as SilentDesk needs them. Bodies are never kept."""

from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class Grant:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
