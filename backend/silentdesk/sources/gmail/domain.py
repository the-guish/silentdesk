"""What a Gmail sync does to the local data. Pure functions over
`VaultData`, so `Store.update` may run them more than once."""

from __future__ import annotations

import re

from ...core.model import GmailMessage, VaultData
from ...core.topics import new_topic, prune_topics
from .api import MessageMeta

# Reply and forward prefixes, as mail clients in several languages write
# them: `Re:`, `RE[2]:`, `Fwd:`, `FW:`, `AW:`, `SV:`, `TR:`.
_PREFIX = re.compile(r"^\s*(?:(?:re|fwd?|aw|sv|tr)\s*(?:\[\d+\])?\s*:\s*)+", re.IGNORECASE)


def thread_title(subject: str) -> str:
    """A thread's subject without reply and forward prefixes."""
    return _PREFIX.sub("", subject).strip() or "(no subject)"


def add_messages(data: VaultData, messages: list[MessageMeta], now: str) -> None:
    """Adds the messages SilentDesk does not have yet. A message joins the
    topic of its Gmail thread, or starts one. Stored messages stay as they
    are."""
    known = {m.message_id for m in data.gmail_messages}
    topic_of = {m.thread_id: m.topic_id for m in data.gmail_messages}
    for meta in messages:
        if meta.message_id in known:
            continue
        known.add(meta.message_id)
        topic_id = topic_of.get(meta.thread_id)
        if topic_id is None:
            topic_id = new_topic(data, thread_title(meta.subject), now)
            topic_of[meta.thread_id] = topic_id
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
    group_threads(data)


def group_threads(data: VaultData) -> None:
    """Puts each thread's messages in one topic, titled by the thread's
    newest subject. A thread whose messages are in several topics, as
    stored before threads were grouped, keeps the topic of its first stored
    message."""
    topic_of: dict[str, str] = {}
    newest: dict[str, GmailMessage] = {}
    for m in data.gmail_messages:
        m.topic_id = topic_of.setdefault(m.thread_id, m.topic_id)
        if m.thread_id not in newest or m.date > newest[m.thread_id].date:
            newest[m.thread_id] = m
    titles = {topic_of[t]: thread_title(m.subject) for t, m in newest.items()}
    for topic in data.topics:
        if topic.id in titles:
            topic.title = titles[topic.id]
    prune_topics(data)


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


def remove_thread(data: VaultData, thread_id: str) -> None:
    """Forgets a thread's messages, and its topic if nothing else is in
    it."""
    data.gmail_messages = [m for m in data.gmail_messages if m.thread_id != thread_id]
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the account, its messages and their topics."""
    data.gmail_account = None
    data.gmail_messages = []
    data.gmail_history_id = None
    prune_topics(data)
