"""What a Slack sync or disconnect does to the stored data. Pure: no I/O,
so `Store.update` may run these more than once."""

from __future__ import annotations

from ...core.model import SlackMessage, VaultData
from ...core.topics import new_topic, prune_topics
from .api import MessageMeta, ts_value

# How many recent direct messages a sync keeps.
SYNC_COUNT = 10


def apply_sync(data: VaultData, latest: list[MessageMeta], now: str) -> None:
    """Replaces the stored Slack messages with `latest`. A conversation is
    one topic: its messages share it, and its title is the newest message's
    preview. A conversation keeps the topic of its newest stored message.
    Topics left without any source item are removed."""
    stored: dict[str, SlackMessage] = {}
    for m in data.slack_messages:
        known = stored.get(m.channel_id)
        if known is None or ts_value(m.ts) > ts_value(known.ts):
            stored[m.channel_id] = m

    topics = {t.id: t for t in data.topics}
    newest: dict[str, MessageMeta] = {}
    topic_of: dict[str, str] = {}
    for meta in latest:
        known = newest.get(meta.channel_id)
        if known is None or ts_value(meta.ts) > ts_value(known.ts):
            newest[meta.channel_id] = meta
    for channel, meta in newest.items():
        title = meta.preview or "(empty message)"
        previous = stored.get(channel)
        topic = topics.get(previous.topic_id) if previous is not None else None
        if topic is None:
            topic_of[channel] = new_topic(data, title, now)
        else:
            topic.title = title
            topic_of[channel] = topic.id

    data.slack_messages = [
        SlackMessage(
            channel_id=meta.channel_id,
            ts=meta.ts,
            topic_id=topic_of[meta.channel_id],
            direction=meta.direction,
            author=meta.author,
            counterpart=meta.counterpart,
            permalink=meta.permalink,
            date=meta.date,
        )
        for meta in latest
    ]
    prune_topics(data)


def clear(data: VaultData) -> None:
    """Forgets the Slack account, its messages and the topics left without
    any source item."""
    data.slack_account = None
    data.slack_messages = []
    prune_topics(data)
