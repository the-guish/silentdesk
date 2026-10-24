"""What a Google Tasks sync does to the local data. Pure functions over
`VaultData`, so `Store.update` may run them more than once."""

from __future__ import annotations

from ...core.model import GoogleTask, VaultData
from ...core.topics import new_topic, prune_topics
from .api import TaskMeta


def apply_sync(data: VaultData, latest: list[TaskMeta], now: str) -> None:
    """Replaces the stored tasks with `latest`. A task that was already
    stored keeps its topic, and the topic follows the task's current title;
    a new task gets a new topic of its own. Topics left without any source
    item are removed."""
    tasks = []
    for meta in latest:
        title = meta.title or "(untitled task)"
        existing = next((t for t in data.google_tasks if t.task_id == meta.task_id), None)
        if existing is not None:
            topic_id = existing.topic_id
            topic = next((t for t in data.topics if t.id == topic_id), None)
            if topic is not None:
                topic.title = title
        else:
            topic_id = new_topic(data, title, now)
        tasks.append(
            GoogleTask(
                task_id=meta.task_id,
                list_id=meta.list_id,
                list_title=meta.list_title,
                topic_id=topic_id,
                due=meta.due,
                origin=meta.origin,
                url=meta.url,
                date=meta.date,
            )
        )
    data.google_tasks = tasks
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the account, its tasks and their topics."""
    data.tasks_account = None
    data.google_tasks = []
    prune_topics(data)
