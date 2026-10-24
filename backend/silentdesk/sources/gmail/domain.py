"""What a Gmail sync does to the local data. Pure functions over
`VaultData`, so `Store.update` may run them more than once."""

from __future__ import annotations

from ...core.model import GmailMessage, VaultData
from ...core.topics import new_topic, prune_topics
from .api import MessageMeta


def add_messages(data: VaultData, messages: list[MessageMeta], now: str) -> None:
    """Adds the messages SilentDesk does not have yet, each with a topic of
    its own (no grouping yet). Stored messages and their topics stay as they
    are."""
    known = {m.message_id for m in data.gmail_messages}
    for meta in messages:
        if meta.message_id in known:
            continue
        known.add(meta.message_id)
        topic_id = new_topic(data, meta.subject or "(no subject)", now)
        data.gmail_messages.append(
            GmailMessage(
                message_id=meta.message_id,
                thread_id=meta.thread_id,
                topic_id=topic_id,
                direction=meta.direction,
                from_=meta.from_,
                to=meta.to,
                subject=meta.subject,
                date=meta.date,
            )
        )


def new_ids(data: VaultData, ids: list[str]) -> list[str]:
    """The IDs in `ids` that are not stored yet, in order and without
    repeats."""
    seen = {m.message_id for m in data.gmail_messages}
    out = []
    for id in ids:
        if id not in seen:
            seen.add(id)
            out.append(id)
    return out


def remove_message(data: VaultData, message_id: str) -> None:
    """Forgets one message, and its topic if nothing else is in it."""
    data.gmail_messages = [m for m in data.gmail_messages if m.message_id != message_id]
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the account, its messages and their topics."""
    data.gmail_account = None
    data.gmail_messages = []
    data.gmail_history_id = None
    prune_topics(data)
