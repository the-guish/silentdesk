"""Gmail messages, as far as SilentDesk needs them: headers and labels only.
Bodies and attachments are never fetched."""

from __future__ import annotations

from dataclasses import dataclass, field

from ....contract import Direction


@dataclass(frozen=True)
class Grant:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    thread_id: str
    # Outbound when Gmail labels it SENT.
    direction: Direction
    # The From header, as written.
    sender: str
    subject: str
    # RFC 3339, from Gmail's internal date.
    date: str


@dataclass(frozen=True)
class Original:
    """The headers of the message a reply answers."""

    direction: Direction
    sender: str
    to: str
    reply_to: str
    subject: str
    # The RFC 5322 Message-ID, not Gmail's ID.
    header_id: str
    references: str
