"""The few Slack Web API calls SilentDesk makes, all read-only."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ...adapters.http import send
from ...core import errors
from ...core.model import Direction

SERVICE = "Slack"
BASE = "https://slack.com/api"

# Longest topic title taken from a message, in characters.
PREVIEW_CHARS = 120


def queries(me: str) -> list[str]:
    """Search queries that together cover direct messages sent to and by the
    user. Results are filtered to direct and group-direct conversations
    afterwards, so a broader match is harmless."""
    return ["to:me", f"from:<@{me}>"]


@dataclass
class Identity:
    user_id: str
    user_name: str
    team_id: str
    team_name: str


@dataclass
class MessageMeta:
    """One direct message, as SilentDesk needs it."""

    channel_id: str
    ts: str
    direction: Direction
    author: str
    # Who the conversation is with: the other person, or "Group DM".
    counterpart: str
    # The start of the message as plain text, used as the topic title.
    preview: str
    permalink: str
    date: str


# --- Response shapes ------------------------------------------------------
#
# Read as strictly as the Rust structs: a missing key takes its default, or
# fails when it has none; a value of the wrong type fails.

_REQUIRED = object()
_STR_OR_NONE = (str, type(None))


def field(obj: Any, key: str, kind: type | tuple[type, ...], default: Any = _REQUIRED) -> Any:
    if not isinstance(obj, dict):
        raise ValueError("invalid type: expected an object")  # noqa: TRY004 - ValueError means a bad response
    if key not in obj:
        if default is _REQUIRED:
            raise ValueError(f"missing field `{key}`")
        return default
    value = obj[key]
    # JSON booleans are not numbers.
    if not isinstance(value, kind) or (isinstance(value, bool) and bool not in _as_tuple(kind)):
        raise ValueError(f"invalid type for field `{key}`")
    return value


def _as_tuple(kind: type | tuple[type, ...]) -> tuple[type, ...]:
    return kind if isinstance(kind, tuple) else (kind,)


@dataclass
class MatchChannel:
    id: str
    # For a 1:1 DM, the other user's ID.
    name: str
    is_im: bool
    is_mpim: bool

    @classmethod
    def parse(cls, obj: Any) -> MatchChannel:
        return cls(
            id=field(obj, "id", str),
            name=field(obj, "name", str, ""),
            is_im=field(obj, "is_im", bool, False),
            is_mpim=field(obj, "is_mpim", bool, False),
        )


@dataclass
class Match:
    kind: str
    channel: MatchChannel
    user: str | None
    username: str | None
    text: str
    ts: str
    permalink: str

    @classmethod
    def parse(cls, obj: Any) -> Match:
        return cls(
            kind=field(obj, "type", str, ""),
            channel=MatchChannel.parse(field(obj, "channel", dict)),
            user=field(obj, "user", _STR_OR_NONE, None),
            username=field(obj, "username", _STR_OR_NONE, None),
            text=field(obj, "text", str, ""),
            ts=field(obj, "ts", str),
            permalink=field(obj, "permalink", str, ""),
        )

    def is_im(self) -> bool:
        return self.kind == "im" or self.channel.is_im

    def is_direct(self) -> bool:
        return self.is_im() or self.channel.is_mpim


@dataclass
class HistoryItem:
    user: str | None
    username: str | None
    text: str
    ts: str
    subtype: str | None

    @classmethod
    def parse(cls, obj: Any) -> HistoryItem:
        return cls(
            user=field(obj, "user", _STR_OR_NONE, None),
            username=field(obj, "username", _STR_OR_NONE, None),
            text=field(obj, "text", str, ""),
            ts=field(obj, "ts", str),
            subtype=field(obj, "subtype", _STR_OR_NONE, None),
        )


def _history(body: Any) -> list[HistoryItem]:
    return [HistoryItem.parse(m) for m in field(body, "messages", list, [])]


def _auth_test(body: Any) -> Identity:
    return Identity(
        user_id=field(body, "user_id", str),
        user_name=field(body, "user", str),
        team_id=field(body, "team_id", str),
        team_name=field(body, "team", str),
    )


def _search_matches(body: Any) -> list[Match]:
    messages = field(body, "messages", dict)
    return [Match.parse(m) for m in field(messages, "matches", list, [])]


def _user_label(body: Any) -> str:
    user = field(body, "user", dict)
    name = field(user, "name", str)
    real_name = field(user, "real_name", str, "")
    profile = field(user, "profile", dict, {})
    candidates = [
        field(profile, "display_name", str, ""),
        field(profile, "real_name", str, ""),
        real_name,
        name,
    ]
    return next((s for s in candidates if s.strip()), "")


# --- Calls ----------------------------------------------------------------


def _visible_ascii(value: str) -> bool:
    return all(c == "\t" or " " <= c <= "~" for c in value)


async def call[T](
    http: httpx.AsyncClient,
    token: str,
    method: str,
    query: list[tuple[str, str]],
    parse: Callable[[Any], T],
) -> T:
    response = await send(
        http,
        "GET",
        f"{BASE}/{method}",
        headers={"Authorization": f"Bearer {token}"},
        params=query,
    )
    status = response.status_code
    if status == 429:
        wait = response.headers.get("retry-after")
        if wait is None or not _visible_ascii(wait):
            wait = "a few"
        raise errors.Api(SERVICE, 429, f"rate limited, try again in {wait} seconds")
    try:
        body = response.json()
    except ValueError:
        raise errors.Network("error decoding response body") from None
    try:
        ok = field(body, "ok", bool)
        error = field(body, "error", _STR_OR_NONE, None)
    except ValueError as e:
        raise errors.Api(SERVICE, status, str(e)) from None
    if not ok:
        error = error if error is not None else "unknown_error"
        if error in ("invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive"):
            raise errors.Reauthorize(SERVICE)
        if error == "missing_scope":
            raise errors.MissingPermission(SERVICE)
        raise errors.Api(SERVICE, status, error)
    try:
        return parse(body)
    except ValueError as e:
        raise errors.Api(SERVICE, status, str(e)) from None


async def identity(http: httpx.AsyncClient, token: str) -> Identity:
    return await call(http, token, "auth.test", [], _auth_test)


async def recent_direct_messages(http: httpx.AsyncClient, token: str, me: str, count: int) -> list[MessageMeta]:
    """The `count` most recent direct messages (1:1 and group), sent or
    received, newest first."""
    page = str(min(count * 3, 100))
    matches: list[Match] = []
    for query in queries(me):
        found = await call(
            http,
            token,
            "search.messages",
            [("query", query), ("sort", "timestamp"), ("sort_dir", "desc"), ("count", page)],
            _search_matches,
        )
        matches.extend(found)
    matches = select_recent(matches, count)

    names = Names()
    return [await to_meta(http, token, me, m, names) for m in matches]


def select_recent(matches: list[Match], count: int) -> list[Match]:
    """Keeps direct messages only, drops duplicates, newest first."""
    seen: set[tuple[str, str]] = set()
    kept = []
    for m in matches:
        key = (m.channel.id, m.ts)
        if m.is_direct() and key not in seen:
            seen.add(key)
            kept.append(m)
    # Stable, like the Rust version: ties keep their order.
    kept.sort(key=lambda m: ts_value(m.ts), reverse=True)
    return kept[:count]


def ts_value(ts: str) -> float:
    try:
        return float(ts)
    except ValueError:
        return 0.0


class Names:
    """Resolves user IDs to display names, once per ID per sync."""

    def __init__(self):
        self.cache: dict[str, str] = {}

    async def get(self, http: httpx.AsyncClient, token: str, id: str) -> str:
        if id in self.cache:
            return self.cache[id]
        try:
            name = await call(http, token, "users.info", [("user", id)], _user_label)
        except errors.AppError:
            name = ""
        name = name or "someone"
        self.cache[id] = name
        return name


async def to_meta(http: httpx.AsyncClient, token: str, me: str, m: Match, names: Names) -> MessageMeta:
    outbound = m.user == me
    if m.user is not None:
        author = await names.get(http, token, m.user)
    elif m.username is not None:
        author = m.username
    else:
        author = "someone"
    if not m.is_im():
        counterpart = "Group DM"
    elif outbound:
        counterpart = await names.get(http, token, m.channel.name)
    else:
        counterpart = author

    mentioned = {}
    for id in mention_ids(m.text):
        mentioned[id] = await names.get(http, token, id)
    return MessageMeta(
        channel_id=m.channel.id,
        ts=m.ts,
        direction=Direction.OUTBOUND if outbound else Direction.INBOUND,
        author=author,
        counterpart=counterpart,
        preview=preview(plain_text(m.text, mentioned), PREVIEW_CHARS),
        permalink=m.permalink,
        date=ts_to_rfc3339(m.ts),
    )


@dataclass
class ConversationMessage:
    """One message of a conversation, read live for the topic screen. It is
    shown, never stored."""

    ts: str
    direction: Direction
    author: str
    text: str
    date: str


# Subtypes that are events, not messages someone wrote.
_EVENT_SUBTYPES = {"channel_join", "channel_leave", "group_join", "group_leave"}


async def conversation(
    http: httpx.AsyncClient, token: str, me: str, channel_id: str, count: int
) -> list[ConversationMessage]:
    """The `count` most recent messages of a conversation, oldest first.
    Needs `im:history` and `mpim:history`."""
    items = await call(
        http,
        token,
        "conversations.history",
        [("channel", channel_id), ("limit", str(count))],
        _history,
    )
    names = Names()
    out = []
    for item in items:
        if item.subtype in _EVENT_SUBTYPES:
            continue
        if item.user is not None:
            author = await names.get(http, token, item.user)
        else:
            author = item.username or "someone"
        mentioned = {id: await names.get(http, token, id) for id in mention_ids(item.text)}
        out.append(
            ConversationMessage(
                ts=item.ts,
                direction=Direction.OUTBOUND if item.user == me else Direction.INBOUND,
                author=author,
                text=plain_text(item.text, mentioned).strip(),
                date=ts_to_rfc3339(item.ts),
            )
        )
    out.sort(key=lambda m: ts_value(m.ts))
    return out


_INTEGER = re.compile(r"[+-]?[0-9]+")


def ts_to_rfc3339(ts: str) -> str:
    head = ts.split(".")[0]
    secs = int(head) if _INTEGER.fullmatch(head) else 0
    try:
        d = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=secs)
    except OverflowError:
        return ""
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}T{d.hour:02d}:{d.minute:02d}:{d.second:02d}Z"


def mention_ids(text: str) -> list[str]:
    """User IDs mentioned as `<@U123>` or `<@U123|name>`."""
    ids = [re.split(r"[>|]", rest, maxsplit=1)[0] for rest in text.split("<@")[1:]]
    return sorted(set(ids))


def plain_text(text: str, names: dict[str, str]) -> str:
    """Turns Slack's message markup into plain text: `<@U1>` → `@Name`,
    `<#C1|general>` → `#general`, `<https://x|label>` → `label`,
    `<!here>` → `@here`, and HTML entities back to characters."""
    out: list[str] = []
    rest = text
    while (start := rest.find("<")) != -1:
        out.append(rest[:start])
        after = rest[start + 1 :]
        end = after.find(">")
        if end == -1:
            out.append(rest[start:])
            rest = ""
            break
        inner = after[:end]
        target, sep, label_text = inner.partition("|")
        label = label_text if sep else None
        if target.startswith("@"):
            id = target[1:]
            name = names.get(id)
            out.append("@" + (name if name is not None else label if label is not None else "someone"))
        elif target.startswith("#"):
            out.append("#" + (label if label is not None else target[1:]))
        elif target.startswith("!"):
            special = target[1:]
            out.append("@" + (label if label is not None else special.split("^")[0]))
        else:
            out.append(label if label is not None else target)
        rest = after[end + 1 :]
    out.append(rest)
    return "".join(out).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def preview(text: str, max: int) -> str:
    """Collapses whitespace and cuts at `max` characters on a word
    boundary."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max:
        return collapsed
    cut = collapsed[:max]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return f"{cut.rstrip()}…"
