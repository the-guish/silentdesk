"""Rules about Slack: which messages, their text, and their topics. See
docs/specs/integrations/slack.md."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from ....contract import Item, Topic
from ..domain.slack import Credential, DirectMessage, Match

SERVICE = "slack"
# search:read finds recent direct messages; users:read turns user IDs into
# names; the history scopes show a conversation. Nothing is written to Slack.
USER_SCOPES = ("search:read", "users:read", "im:history", "mpim:history")
# How many recent direct messages a sync keeps.
SYNC_COUNT = 10
# Longest topic title taken from a message, in characters.
PREVIEW_CHARS = 120
# Refresh a little before the access token expires, in seconds.
EXPIRY_MARGIN = 60
# How many recent messages the topic screen shows.
HISTORY_COUNT = 50
# Subtypes that are events, not messages someone wrote.
EVENT_SUBTYPES = {"channel_join", "channel_leave", "group_join", "group_leave"}


def queries(me: str) -> list[str]:
    """Searches that together find direct messages sent to and by the user.
    Results are filtered to direct conversations afterwards."""
    return ["to:me", f"from:<@{me}>"]


def needs_refresh(credential: Credential, now: int) -> bool:
    return (
        credential.refresh_token is not None
        and credential.expires_at is not None
        and now >= credential.expires_at - EXPIRY_MARGIN
    )


def ts_value(ts: str) -> float:
    try:
        return float(ts)
    except ValueError:
        return 0.0


def ts_to_rfc3339(ts: str) -> str:
    return datetime.fromtimestamp(int(ts_value(ts)), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_recent(matches: Iterable[Match], count: int) -> list[Match]:
    """Direct messages only (1:1 and group), without repeats, newest first."""
    seen: set[tuple[str, str]] = set()
    kept = []
    for match in matches:
        if (match.is_im or match.is_mpim) and (match.channel_id, match.ts) not in seen:
            seen.add((match.channel_id, match.ts))
            kept.append(match)
    kept.sort(key=lambda match: ts_value(match.ts), reverse=True)
    return kept[:count]


def mention_ids(text: str) -> list[str]:
    """User IDs mentioned as <@U123> or <@U123|name>."""
    return sorted({re.split(r"[>|]", rest, maxsplit=1)[0] for rest in text.split("<@")[1:]})


def plain_text(text: str, names: Mapping[str, str]) -> str:
    """Slack's markup as plain text: <@U1> becomes @Name, <#C1|general>
    #general, <https://x|label> label, <!here> @here, and HTML entities
    their characters."""
    out, rest = [], text
    while (start := rest.find("<")) != -1:
        out.append(rest[:start])
        after = rest[start + 1 :]
        end = after.find(">")
        if end == -1:
            out.append(rest[start:])
            rest = ""
            break
        target, separator, label = after[:end].partition("|")
        label = label if separator else None
        if target.startswith("@"):
            out.append("@" + (names.get(target[1:]) or label or "someone"))
        elif target.startswith("#"):
            out.append("#" + (label or target[1:]))
        elif target.startswith("!"):
            out.append("@" + (label or target[1:].split("^")[0]))
        else:
            out.append(label or target)
        rest = after[end + 1 :]
    out.append(rest)
    return "".join(out).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    """Whitespace collapsed, cut at `limit` characters on a word boundary."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip() + "…"


def topics(messages: Iterable[DirectMessage]) -> list[Topic]:
    """One topic per conversation, titled with its newest message's preview."""
    conversations: dict[str, list[DirectMessage]] = {}
    for message in messages:
        conversations.setdefault(message.channel_id, []).append(message)
    out = []
    for channel_id, found in conversations.items():
        found.sort(key=lambda message: ts_value(message.ts))
        # Read-only: SilentDesk has no scope to delete a Slack message.
        items = [Item(m.ts, m.direction, m.author or None, m.permalink or None, m.date, False) for m in found]
        out.append(Topic(channel_id, found[-1].preview or "(empty message)", items, deletable=False))
    return out
