"""What a Slack sync or disconnect does to the stored data. Pure: no I/O,
so `Store.update` may run these more than once."""

from __future__ import annotations

from ...core.model import SlackMessage, VaultData
from ...core.topics import new_topic, prune_topics
from .api import MessageMeta

# How many recent direct messages a sync keeps.
SYNC_COUNT = 10


def apply_sync(data: VaultData, latest: list[MessageMeta], now: str) -> None:
    """Replaces the stored Slack messages with `latest`. A message that was
    already stored keeps its topic; a new message gets a new topic of its
    own (no grouping yet). Topics left without any source item are
    removed."""
    messages = []
    for meta in latest:
        existing = next(
            (m for m in data.slack_messages if m.channel_id == meta.channel_id and m.ts == meta.ts),
            None,
        )
        if existing is not None:
            topic_id = existing.topic_id
        else:
            topic_id = new_topic(data, meta.preview or "(empty message)", now)
        messages.append(
            SlackMessage(
                channel_id=meta.channel_id,
                ts=meta.ts,
                topic_id=topic_id,
                direction=meta.direction,
                author=meta.author,
                counterpart=meta.counterpart,
                permalink=meta.permalink,
                date=meta.date,
            )
        )
    data.slack_messages = messages
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the Slack account, its messages and the topics left without
    any source item."""
    data.slack_account = None
    data.slack_messages = []
    prune_topics(data)
