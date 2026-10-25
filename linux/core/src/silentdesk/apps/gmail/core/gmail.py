"""Rules about Gmail: threads as topics, and replies. See
spec/integrations/gmail.md."""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable, Sequence

from ....contract import Direction, Item, Topic
from ..domain.gmail import GmailMessage, Original

SERVICE = "gmail"
# gmail.modify reads headers and moves messages to the trash; it cannot
# delete them for good. gmail.send sends replies.
SCOPES = ("https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send")


def new_ids(known: set[str], ids: Iterable[str]) -> list[str]:
    """The IDs not known yet, in order and without repeats."""
    seen, out = set(known), []
    for message_id in ids:
        if message_id not in seen:
            seen.add(message_id)
            out.append(message_id)
    return out


def topic(thread_id: str, messages: Sequence[GmailMessage]) -> Topic:
    """One topic per thread, its messages oldest first, titled with the
    first message's subject."""
    ordered = sorted(messages, key=lambda message: (message.date, message.message_id))
    items = [
        Item(
            key=message.message_id,
            direction=message.direction,
            author=sender_name(message.sender) or None,
            url=f"https://mail.google.com/mail/#all/{thread_id}",
            date=message.date,
            # gmail.modify moves any message to the trash.
            deletable=True,
        )
        for message in ordered
    ]
    return Topic(key=thread_id, title=ordered[0].subject.strip() or "(no subject)", items=items, deletable=True)


def sender_name(sender: str) -> str:
    """`Ana Ruiz <ana@example.com>` -> `Ana Ruiz`; a bare address stays as is."""
    name, _, address = sender.partition("<")
    return name.strip().strip('"') or address.rstrip(">").strip()


def recipient(original: Original) -> str:
    """The sender (or its Reply-To) of a received email, and the original
    recipients of one the user sent. There is no reply-all yet."""
    if original.direction == Direction.OUTBOUND:
        return original.to
    return original.reply_to if original.reply_to.strip() else original.sender


def reply_subject(subject: str) -> str:
    trimmed = subject.strip()
    if not trimmed:
        return "Re:"
    return trimmed if trimmed[:3].lower() == "re:" else f"Re: {trimmed}"


def clean(value: str) -> str:
    """Header values stay on one line, or they could inject headers."""
    return " ".join(part.strip() for part in re.split(r"[\r\n]", value) if part.strip())


def encode_word(value: str) -> str:
    """RFC 2047 encoding for a header with non-ASCII text."""
    return value if value.isascii() else f"=?UTF-8?B?{base64.b64encode(value.encode()).decode()}?="


def reply(original: Original, body: str) -> str:
    """The RFC 5322 reply, with CRLF line endings. Nothing is quoted, so the
    original's body is never read. Gmail fills in From and Date."""
    headers = [("To", clean(recipient(original))), ("Subject", encode_word(clean(reply_subject(original.subject))))]
    header_id = clean(original.header_id)
    if header_id:
        headers += [("In-Reply-To", header_id), ("References", clean(f"{original.references} {header_id}"))]
    headers += [
        ("MIME-Version", "1.0"),
        ("Content-Type", "text/plain; charset=UTF-8"),
        ("Content-Transfer-Encoding", "base64"),
    ]
    encoded = base64.b64encode(body.replace("\r\n", "\n").replace("\n", "\r\n").encode()).decode()
    lines = [encoded[i : i + 76] for i in range(0, len(encoded), 76)]
    return (
        "".join(f"{name}: {value}\r\n" for name, value in headers) + "\r\n" + "".join(f"{line}\r\n" for line in lines)
    )
