"""Which topics a query lists: search text and filters. Pure, so it is
tested without storage."""

from __future__ import annotations

from ....contract import Direction, TopicQuery
from ..domain.topics import TopicRecord

# The names people know the services by, which search matches too.
SERVICE_NAMES = {"gmail": "Gmail", "github": "GitHub", "jira": "Jira", "slack": "Slack", "tasks": "Google Tasks"}


def search_text(record: TopicRecord) -> str:
    """Everything a search matches against, lowercased."""
    parts = [record.title, SERVICE_NAMES.get(record.service, record.service)]
    parts += [part for item in record.items for part in (item.author, item.key) if part]
    return "\n".join(parts).lower()


def waiting_on(record: TopicRecord) -> str:
    """Who the topic waits on: "others" when the user wrote last, else "me"."""
    newest = record.items[-1] if record.items else None
    return "others" if newest and newest.direction == Direction.OUTBOUND else "me"


def matches(record: TopicRecord, deletable: bool, query: TopicQuery) -> bool:
    """Whether the topic has every word of the search and passes every filter."""
    if query.services and record.service not in query.services:
        return False
    if query.people and not any(item.author in query.people for item in record.items):
        return False
    if query.waiting_on and waiting_on(record) not in query.waiting_on:
        return False
    # RFC 3339 times in UTC sort as text.
    if query.updated_from is not None and record.updated_at < query.updated_from:
        return False
    if query.updated_to is not None and record.updated_at >= query.updated_to:
        return False
    if query.deletable is not None and deletable != query.deletable:
        return False
    words = query.text.lower().split()
    if words:
        text = search_text(record)
        return all(word in text for word in words)
    return True
