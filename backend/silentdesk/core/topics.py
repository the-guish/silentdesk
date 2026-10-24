"""Topic bookkeeping shared by every source, and the Topics list the UI
shows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from .model import Topic, VaultData, to_json


def now_rfc3339() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_topic(data: VaultData, title: str, now: str) -> str:
    """Adds a topic and returns its id."""
    topic = Topic(id=str(uuid.uuid4()), title=title, created_at=now)
    data.topics.append(topic)
    return topic.id


def prune_topics(data: VaultData) -> None:
    """Drops topics that no source item points to any more."""
    used = {
        *(m.topic_id for m in data.gmail_messages),
        *(m.topic_id for m in data.slack_messages),
        *(i.topic_id for i in data.jira_issues),
        *(p.topic_id for p in data.pull_requests),
        *(t.topic_id for t in data.google_tasks),
    }
    data.topics = [t for t in data.topics if t.id in used]


def topic_views(data: VaultData) -> list[dict[str, Any]]:
    """Topics with their source items, most recent activity first, as JSON
    for the UI."""
    groups = {
        "emails": data.gmail_messages,
        "slackMessages": data.slack_messages,
        "jiraIssues": data.jira_issues,
        "pullRequests": data.pull_requests,
        "googleTasks": data.google_tasks,
    }
    by_topic: dict[str, dict[str, list]] = {}
    for key, items in groups.items():
        for item in items:
            by_topic.setdefault(item.topic_id, {}).setdefault(key, []).append(item)

    views = []
    for topic in data.topics:
        items = by_topic.get(topic.id, {})
        view: dict[str, Any] = to_json(topic)
        latest = None
        for key in groups:
            sorted_items = sorted(items.get(key, []), key=lambda i: i.date, reverse=True)
            view[key] = to_json(sorted_items)
            if sorted_items and (latest is None or sorted_items[0].date > latest):
                latest = sorted_items[0].date
        views.append((latest or topic.created_at, view))
    # Stable, like the Rust version: ties keep their stored order.
    views.sort(key=lambda pair: pair[0], reverse=True)
    return [view for _, view in views]
