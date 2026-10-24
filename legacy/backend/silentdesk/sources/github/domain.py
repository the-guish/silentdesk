"""What a GitHub sync does to the local data. Pure: no I/O."""

from __future__ import annotations

from ...core.model import PullRequest, VaultData
from ...core.topics import new_topic, prune_topics
from .api import PullMeta


def apply_sync(data: VaultData, latest: list[PullMeta], now: str) -> None:
    """Replaces the stored pull requests with `latest`. A pull request that
    was already stored keeps its topic; a new one gets a new topic of its
    own, titled with its title. Topics left without any source item are
    removed."""
    pulls = []
    for meta in latest:
        existing = next((p for p in data.pull_requests if p.pr_id == meta.pr_id), None)
        if existing is not None:
            topic_id = existing.topic_id
        else:
            topic_id = new_topic(data, meta.title or f"{meta.repo}#{meta.number}", now)
        pulls.append(
            PullRequest(
                pr_id=meta.pr_id,
                repo=meta.repo,
                number=meta.number,
                topic_id=topic_id,
                reason=meta.reason,
                direction=meta.direction,
                draft=meta.draft,
                author=meta.author,
                url=meta.url,
                date=meta.date,
            )
        )
    data.pull_requests = pulls
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the GitHub account, its pull requests and the topics only
    they held."""
    data.github_account = None
    data.pull_requests = []
    prune_topics(data)
