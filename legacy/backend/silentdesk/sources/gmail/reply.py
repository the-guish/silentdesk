"""Builds the RFC 2822 message for a reply. The user types the body; nothing
is quoted from the original, so its body is never read."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

from ...core.model import Direction


@dataclass
class Original:
    """The headers of the message being answered."""

    direction: Direction
    from_: str
    to: str
    reply_to: str
    subject: str
    # The RFC 2822 `Message-ID`, not Gmail's ID.
    message_id: str
    references: str


def recipient(original: Original) -> str:
    """Who gets the reply: the sender (or its `Reply-To`) for a received
    email, and the original recipients for one the user sent."""
    if original.direction == Direction.OUTBOUND:
        return original.to
    if original.reply_to.strip():
        return original.reply_to
    return original.from_


def subject(original: str) -> str:
    trimmed = original.strip()
    prefix = trimmed[:3]
    if not trimmed:
        return "Re:"
    if prefix.isascii() and prefix.lower() == "re:":
        return trimmed
    return f"Re: {trimmed}"


def build(original: Original, body: str) -> str:
    """The full message, with CRLF line endings. Gmail fills in `From` and
    `Date`."""
    headers = [
        ("To", clean(recipient(original))),
        ("Subject", encode_word(clean(subject(original.subject)))),
    ]
    message_id = clean(original.message_id)
    if message_id:
        references = clean(f"{original.references} {message_id}")
        headers.append(("In-Reply-To", message_id))
        headers.append(("References", references.strip()))
    headers.append(("MIME-Version", "1.0"))
    headers.append(("Content-Type", "text/plain; charset=UTF-8"))
    headers.append(("Content-Transfer-Encoding", "base64"))

    out = "".join(f"{name}: {value}\r\n" for name, value in headers)
    out += "\r\n"
    normalized = body.replace("\r\n", "\n").replace("\n", "\r\n")
    encoded = base64.b64encode(normalized.encode()).decode()
    for i in range(0, len(encoded), 76):
        out += encoded[i : i + 76] + "\r\n"
    return out


def clean(value: str) -> str:
    """Header values must stay on one line, or they could inject headers."""
    parts = (s.strip() for s in re.split(r"[\r\n]", value))
    return " ".join(s for s in parts if s)


def encode_word(value: str) -> str:
    """RFC 2047 encoding for a header with non-ASCII text."""
    if value.isascii():
        return value
    return f"=?UTF-8?B?{base64.b64encode(value.encode()).decode()}?="
