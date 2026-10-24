"""What a Jira sync does to the local data. Pure: no I/O."""

from __future__ import annotations

from ...core.model import JiraIssue, VaultData
from ...core.topics import new_topic, prune_topics
from .api import IssueMeta

# How many open issues a sync keeps.
SYNC_COUNT = 10


def apply_sync(data: VaultData, latest: list[IssueMeta], now: str) -> None:
    """Replaces the stored Jira issues with `latest`. An issue that was
    already stored keeps its topic; a new issue gets a new topic of its own,
    titled with its summary. Topics left without any source item are
    removed."""
    issues = []
    for meta in latest:
        existing = next((i for i in data.jira_issues if i.issue_id == meta.issue_id), None)
        if existing is not None:
            topic_id = existing.topic_id
        else:
            topic_id = new_topic(data, meta.summary or meta.key, now)
        issues.append(
            JiraIssue(
                issue_id=meta.issue_id,
                key=meta.key,
                topic_id=topic_id,
                direction=meta.direction,
                status=meta.status,
                project=meta.project,
                assignee=meta.assignee,
                reporter=meta.reporter,
                url=meta.url,
                date=meta.date,
            )
        )
    data.jira_issues = issues
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the Jira account, its issues and the topics only they held."""
    data.jira_account = None
    data.jira_issues = []
    prune_topics(data)
