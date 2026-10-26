"""Which topics a query lists: search text and filters. Pure, so it is
tested without storage."""

from __future__ import annotations

import re
from datetime import datetime

from ....contract import DEFAULT_PROJECT, Direction, InvalidQuery, TopicQuery
from ..domain.topics import TopicRecord

# The names people know the services by, which search matches too.
SERVICE_NAMES = {"gmail": "Gmail", "github": "GitHub", "jira": "Jira", "slack": "Slack", "tasks": "Google Tasks"}

RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})")


def instant(text: str) -> datetime:
    """An RFC 3339 time. Raises `InvalidQuery` for anything else."""
    if not RFC3339.fullmatch(text):
        raise InvalidQuery(f"{text!r} is not an RFC 3339 time.")
    return datetime.fromisoformat(text.upper())


def check(query: TopicQuery) -> None:
    """Raises `InvalidQuery` for a query whose times are not RFC 3339."""
    for bound in (query.updated_from, query.updated_to):
        if bound is not None:
            instant(bound)


def search_text(record: TopicRecord) -> str:
    """Everything a search matches against, lowercased."""
    parts = [record.title, SERVICE_NAMES.get(record.service, record.service)]
    if record.status:
        parts.append(record.status.name)
    parts += [part for item in record.items for part in (item.author, item.key) if part]
    return "\n".join(parts).lower()


def waiting_on(record: TopicRecord) -> str:
    """Who the topic waits on: "others" when the user wrote last, else "me"."""
    newest = record.items[-1] if record.items else None
    return "others" if newest and newest.direction == Direction.OUTBOUND else "me"


def matches(record: TopicRecord, deletable: bool, query: TopicQuery) -> bool:
    """Whether the topic has every word of the search and passes every filter."""
    if query.projects and (record.project_id or DEFAULT_PROJECT) not in query.projects:
        return False
    if query.services and record.service not in query.services:
        return False
    if query.people and not any(item.author in query.people for item in record.items):
        return False
    if query.waiting_on and waiting_on(record) not in query.waiting_on:
        return False
    if query.updated_from is not None or query.updated_to is not None:
        # Connectors store RFC 3339 times, in UTC.
        updated = datetime.fromisoformat(record.updated_at)
        if query.updated_from is not None and updated < instant(query.updated_from):
            return False
        if query.updated_to is not None and updated >= instant(query.updated_to):
            return False
    if query.deletable is not None and deletable != query.deletable:
        return False
    words = query.text.lower().split()
    if words:
        text = search_text(record)
        return all(word in text for word in words)
    return True
