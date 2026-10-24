"""The few Gmail API calls SilentDesk makes. Reads ask for headers only;
message bodies are never fetched. The topic screen also shows Gmail's
snippet of each message, read live and never stored."""

from __future__ import annotations

import asyncio
import base64
import email.utils
import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ...adapters.http import send as http_send
from ...core import errors
from ...core.model import Direction
from . import wire
from .reply import Original

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Google allows 15,000 quota units per user per minute, and reading one
# message costs 5: 50 messages a second. Staying at 40 leaves room for
# other calls. Seconds.
READ_PACE = 0.025
MAX_IN_FLIGHT = 20
# Waits after a rate-limit or server error: 1, 2, 4, 8 and 16 seconds.
RETRIES = 5

# The waits between retries; tests replace it.
sleep = asyncio.sleep


@dataclass
class MessageMeta:
    """Headers and labels for one message, as SilentDesk needs them."""

    message_id: str
    thread_id: str
    direction: Direction
    from_: str
    to: str
    subject: str
    date: str


@dataclass
class Profile:
    email_address: str
    # Marks the mailbox's current state; changes after it can be listed.
    history_id: str


def _profile(value: Any) -> Profile:
    o = wire.obj(value)
    return Profile(wire.string(o, "emailAddress"), wire.string(o, "historyId"))


@dataclass
class MessageId:
    id: str
    label_ids: list[str]


def _message_id(value: Any) -> MessageId:
    o = wire.obj(value)
    return MessageId(wire.string(o, "id"), wire.strings(o, "labelIds"))


@dataclass
class MessageList:
    messages: list[MessageId]
    next_page_token: str | None


def _message_list(value: Any) -> MessageList:
    o = wire.obj(value)
    return MessageList(wire.items(o, "messages", _message_id), wire.opt_string(o, "nextPageToken"))


@dataclass
class HistoryRecord:
    messages_added: list[MessageId]
    labels_added: list[MessageId]


def _history_message(value: Any) -> MessageId:
    o = wire.obj(value)
    if "message" not in o:
        raise wire.Malformed
    return _message_id(o["message"])


def _history_record(value: Any) -> HistoryRecord:
    o = wire.obj(value)
    return HistoryRecord(
        wire.items(o, "messagesAdded", _history_message),
        wire.items(o, "labelsAdded", _history_message),
    )


@dataclass
class HistoryList:
    history: list[HistoryRecord]
    next_page_token: str | None
    history_id: str


def _history_list(value: Any) -> HistoryList:
    o = wire.obj(value)
    return HistoryList(
        wire.items(o, "history", _history_record),
        wire.opt_string(o, "nextPageToken"),
        wire.string(o, "historyId"),
    )


@dataclass
class RawMessage:
    id: str
    thread_id: str
    label_ids: list[str]
    internal_date: str | None
    # `(name, value)` pairs; empty when the message has no payload.
    headers: list[tuple[str, str]]
    # Gmail's plain-text preview of the body, with HTML entities.
    snippet: str = ""


def _header(value: Any) -> tuple[str, str]:
    o = wire.obj(value)
    return wire.string(o, "name"), wire.string(o, "value")


def _raw_message(value: Any) -> RawMessage:
    o = wire.obj(value)
    payload = o.get("payload")
    headers = [] if payload is None else wire.items(wire.obj(payload), "headers", _header)
    return RawMessage(
        id=wire.string(o, "id"),
        thread_id=wire.string(o, "threadId"),
        label_ids=wire.strings(o, "labelIds"),
        internal_date=wire.opt_string(o, "internalDate"),
        headers=headers,
        snippet=wire.string(o, "snippet", ""),
    )


def _thread(value: Any) -> list[RawMessage]:
    return wire.items(wire.obj(value), "messages", _raw_message)


@dataclass
class ThreadMessage:
    """One message of a thread, read live for the topic screen. It is shown,
    never stored."""

    id: str
    direction: Direction
    # The sender's name, or their address when the name is missing.
    author: str
    # Gmail's snippet: the start of the body as plain text.
    text: str
    date: str


async def _get[T](
    http: httpx.AsyncClient,
    token: str,
    url: str,
    query: list[tuple[str, str]],
    parse: Callable[[Any], T],
) -> T:
    response = await _send_request(http, "GET", url, token, params=query)
    return wire.read_json(response, parse)


async def _post(http: httpx.AsyncClient, token: str, url: str, body: dict[str, Any]) -> None:
    await _send_request(http, "POST", url, token, json=body)


async def _send_request(http: httpx.AsyncClient, method: str, url: str, token: str, **kwargs) -> httpx.Response:
    """Sends the request, and sends it again after rate-limit and server
    errors."""
    headers = {"Authorization": f"Bearer {token}"}
    attempt = 0
    while True:
        response = await http_send(http, method, url, headers=headers, **kwargs)
        if response.is_success:
            return response
        error = _api_error(response)
        if attempt < RETRIES and is_transient(error):
            await sleep(1 << attempt)
            attempt += 1
            continue
        raise error


def is_transient(error: errors.AppError) -> bool:
    if isinstance(error, errors.Api):
        return error.status in (429, 500, 502, 503, 504) or (
            error.status == 403 and "rate limit" in error.message.lower()
        )
    return False


def is_not_found(error: errors.AppError) -> bool:
    return isinstance(error, errors.Api) and error.status == 404


def _error_message(response: httpx.Response) -> str:
    try:
        return wire.string(wire.obj(wire.obj(response.json()).get("error")), "message")
    except (ValueError, wire.Malformed):
        return httpx.codes.get_reason_phrase(response.status_code) or "unknown error"


def _api_error(response: httpx.Response) -> errors.AppError:
    status = response.status_code
    if status == 401:
        return errors.Reauthorize("Gmail")
    message = _error_message(response)
    # Accounts connected before trash and reply existed lack the scopes.
    if status == 403 and "insufficient authentication scopes" in message:
        return errors.MissingPermission("Gmail")
    return errors.Api("Gmail", status, message)


async def profile(http: httpx.AsyncClient, token: str) -> Profile:
    return await _get(http, token, f"{BASE}/profile", [], _profile)


async def inbox_ids(http: httpx.AsyncClient, token: str) -> list[str]:
    """The IDs of every message in the Inbox, newest first."""
    ids: list[str] = []
    page: str | None = None
    while True:
        query = [("labelIds", "INBOX"), ("maxResults", "500")]
        if page is not None:
            query.append(("pageToken", page))
        listing = await _get(http, token, f"{BASE}/messages", query, _message_list)
        ids.extend(m.id for m in listing.messages)
        if listing.next_page_token is None:
            return ids
        page = listing.next_page_token


async def inbox_changes(http: httpx.AsyncClient, token: str, start: str) -> tuple[list[str], str] | None:
    """Messages that entered the Inbox since `start`, and the history ID to
    start from next time. `None` when Gmail no longer keeps history that old
    (about a week); a full listing is needed then."""
    history: list[HistoryRecord] = []
    page: str | None = None
    while True:
        query = [
            ("startHistoryId", start),
            ("labelId", "INBOX"),
            ("historyTypes", "messageAdded"),
            ("historyTypes", "labelAdded"),
        ]
        if page is not None:
            query.append(("pageToken", page))
        try:
            listing = await _get(http, token, f"{BASE}/history", query, _history_list)
        except errors.Api as e:
            if is_not_found(e):
                return None
            raise
        history.extend(listing.history)
        if listing.next_page_token is None:
            return inbox_additions(history), listing.history_id
        page = listing.next_page_token


def inbox_additions(history: list[HistoryRecord]) -> list[str]:
    seen: set[str] = set()
    out = []
    for record in history:
        for m in [*record.messages_added, *record.labels_added]:
            if "INBOX" in m.label_ids and m.id not in seen:
                seen.add(m.id)
                out.append(m.id)
    return out


class _Pace:
    """Lets one call through every `period` seconds. A late call delays the
    ones after it rather than letting them burst (tokio's
    `MissedTickBehavior::Delay`)."""

    def __init__(self, period: float):
        self.period = period
        self.next: float | None = None

    async def tick(self) -> None:
        now = asyncio.get_running_loop().time()
        if self.next is None or now >= self.next:
            self.next = now + self.period
            return
        await asyncio.sleep(self.next - now)
        self.next += self.period


async def subjects(
    http: httpx.AsyncClient,
    token: str,
    ids: list[str],
    progress: Callable[[int], None],
) -> list[MessageMeta]:
    """Subject, labels and date of each message in `ids`, read in parallel
    at the pace Google allows. Drafts, chats and messages deleted in the
    meantime are left out. `progress` gets the number of messages read so
    far."""

    async def read(id: str) -> MessageMeta | None:
        query = [("format", "metadata"), ("metadataHeaders", "Subject")]
        try:
            raw = await _get(http, token, f"{BASE}/messages/{id}", query, _raw_message)
        except errors.Api as e:
            if is_not_found(e):
                return None
            raise
        return to_meta(raw)

    pace = _Pace(READ_PACE)
    pending = (id for id in ids if is_gmail_id(id))
    tasks: set[asyncio.Task[MessageMeta | None]] = set()
    out: list[MessageMeta] = []
    done = 0
    try:
        while True:
            while len(tasks) < MAX_IN_FLIGHT:
                id = next(pending, None)
                if id is None:
                    break
                await pace.tick()
                tasks.add(asyncio.create_task(read(id)))
            if not tasks:
                return out
            finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in finished:
                tasks.remove(task)
                meta = task.result()
                if meta is not None:
                    out.append(meta)
                done += 1
                progress(done)
    finally:
        # On error, stop the reads still in flight.
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def trash_thread(http: httpx.AsyncClient, token: str, thread_id: str) -> None:
    """Moves every message of a thread to the trash, as Gmail's own
    conversation view does. A thread that no longer exists counts as
    trashed."""
    if not is_gmail_id(thread_id):
        raise errors.UnknownMessage()
    try:
        await _post(http, token, f"{BASE}/threads/{thread_id}/trash", {})
    except errors.Api as e:
        if not is_not_found(e):
            raise


async def thread(http: httpx.AsyncClient, token: str, thread_id: str) -> list[ThreadMessage]:
    """Every message of a thread, oldest first, with sender, date and
    snippet. Drafts and chats are left out. A thread that no longer exists
    has no messages."""
    if not is_gmail_id(thread_id):
        raise errors.UnknownMessage()
    query = [("format", "metadata"), ("metadataHeaders", "From")]
    try:
        raws = await _get(http, token, f"{BASE}/threads/{thread_id}", query, _thread)
    except errors.Api as e:
        if is_not_found(e):
            return []
        raise
    out: list[tuple[int, ThreadMessage]] = []
    for raw in raws:
        meta = to_meta(raw)
        if meta is None:
            continue
        name, address = email.utils.parseaddr(meta.from_)
        # `to_meta` checked that the internal date is an integer.
        millis = int(raw.internal_date or 0)
        out.append(
            (
                millis,
                ThreadMessage(
                    id=raw.id,
                    direction=meta.direction,
                    author=name or address or "(unknown sender)",
                    text=html.unescape(raw.snippet),
                    date=meta.date,
                ),
            )
        )
    out.sort(key=lambda pair: pair[0])
    return [m for _, m in out]


async def original(http: httpx.AsyncClient, token: str, id: str) -> Original:
    """The headers a reply to message `id` needs."""
    if not is_gmail_id(id):
        raise errors.UnknownMessage()
    raw = await _get(
        http,
        token,
        f"{BASE}/messages/{id}",
        [
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "To"),
            ("metadataHeaders", "Reply-To"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Message-ID"),
            ("metadataHeaders", "References"),
        ],
        _raw_message,
    )
    return to_original(raw)


async def send(http: httpx.AsyncClient, token: str, thread_id: str, message: str) -> None:
    """Sends `message` (RFC 2822) in the thread `thread_id`."""
    await _post(
        http,
        token,
        f"{BASE}/messages/send",
        {
            "raw": base64.urlsafe_b64encode(message.encode()).decode(),
            "threadId": thread_id,
        },
    )


_GMAIL_ID = re.compile(r"[A-Za-z0-9]+")


def is_gmail_id(id: str) -> bool:
    """Gmail IDs are hex strings. Checking keeps anything unexpected out of
    URLs."""
    return _GMAIL_ID.fullmatch(id) is not None


def header(raw: RawMessage, name: str) -> str:
    for h_name, value in raw.headers:
        if h_name.isascii() and h_name.lower() == name.lower():
            return value.strip()
    return ""


def direction(raw: RawMessage) -> Direction:
    return Direction.OUTBOUND if "SENT" in raw.label_ids else Direction.INBOUND


def to_original(raw: RawMessage) -> Original:
    return Original(
        direction=direction(raw),
        from_=header(raw, "From"),
        to=header(raw, "To"),
        reply_to=header(raw, "Reply-To"),
        subject=header(raw, "Subject"),
        message_id=header(raw, "Message-ID"),
        references=header(raw, "References"),
    )


_INTEGER = re.compile(r"[+-]?[0-9]+")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def rfc3339_from_millis(ms: str | None) -> str | None:
    """Gmail's internal date (milliseconds since the epoch, as a string) in
    RFC 3339, with as many fraction digits as needed, like the `time`
    crate. `None` when it is missing or out of range."""
    if ms is None or _INTEGER.fullmatch(ms) is None:
        return None
    try:
        d = _EPOCH + timedelta(milliseconds=int(ms))
    except OverflowError:
        return None
    out = f"{d.year:04d}-{d.month:02d}-{d.day:02d}T{d.hour:02d}:{d.minute:02d}:{d.second:02d}"
    millis = d.microsecond // 1000
    if millis:
        out += "." + f"{millis:03d}".rstrip("0")
    return out + "Z"


def to_meta(raw: RawMessage) -> MessageMeta | None:
    if "DRAFT" in raw.label_ids or "CHAT" in raw.label_ids:
        return None
    date = rfc3339_from_millis(raw.internal_date)
    if date is None:
        return None
    return MessageMeta(
        message_id=raw.id,
        thread_id=raw.thread_id,
        direction=direction(raw),
        from_=header(raw, "From"),
        to=header(raw, "To"),
        subject=header(raw, "Subject"),
        date=date,
    )
