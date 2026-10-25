"""The few Gmail API calls SilentDesk makes, ported from the legacy backend.
Reads ask for headers only; bodies are never fetched."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ....contract import AuthError, Direction, Http, NetworkError, RemoteError
from ..domain.gmail import GmailMessage, Original
from ..ports.gmail_api import GmailApi, Profile

SERVICE = "gmail"
# Google allows 15,000 quota units per user per minute, and reading one
# message costs 5: 50 a second. Staying at 40 leaves room for other calls.
READ_PACE = 0.025
MAX_IN_FLIGHT = 20
# Waits after a rate-limit or server error: 1, 2, 4, 8, 16 and 32 seconds,
# over a minute in all, as Google counts quota per minute.
RETRIES = 6
# The reasons a 403 gives when a per-minute quota runs out.
RATE_LIMITS = ("rateLimitExceeded", "userRateLimitExceeded")
GMAIL_ID = re.compile(r"[A-Za-z0-9]+")


def is_gmail_id(value: str) -> bool:
    """Gmail IDs are hex strings; anything else is kept out of URLs."""
    return GMAIL_ID.fullmatch(value) is not None


class _Pace:
    """Lets one call through every `period` seconds; a late call delays the
    next ones rather than letting them burst."""

    def __init__(self, period: float) -> None:
        self.period, self.next = period, None

    async def tick(self) -> None:
        now = asyncio.get_running_loop().time()
        if self.next is None or now >= self.next:
            self.next = now + self.period
            return
        await asyncio.sleep(self.next - now)
        self.next += self.period


def _date(millis: Any) -> str | None:
    """Gmail's internal date, milliseconds since the epoch, in RFC 3339."""
    if not isinstance(millis, str) or not millis.isdigit():
        return None
    moment = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=int(millis))
    fraction = f".{moment.microsecond // 1000:03d}".rstrip("0").rstrip(".")
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + fraction + "Z"


def _header(message: dict[str, Any], name: str) -> str:
    payload = message.get("payload")
    for header in payload.get("headers", []) if isinstance(payload, dict) else []:
        if isinstance(header, dict) and str(header.get("name", "")).lower() == name.lower():
            return str(header.get("value", "")).strip()
    return ""


def _direction(message: dict[str, Any]) -> Direction:
    return Direction.OUTBOUND if "SENT" in message.get("labelIds", []) else Direction.INBOUND


class GmailHttpApi(GmailApi):
    def __init__(self, http: Http, base_url: str, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.http = http
        self.base = f"{base_url}/gmail/v1/users/me"
        # Waits between retries; tests pass one that does not wait.
        self.sleep = sleep
        # After a rate-limit, every call waits until then, not only the one
        # that hit it: the quota is per user.
        self.paused_until = 0.0

    async def _call(self, method: str, path: str, token: str, **kwargs: Any) -> Any:
        """Sends the request, again after rate-limit and server errors."""
        for attempt in range(RETRIES + 1):
            if (pause := self.paused_until - asyncio.get_running_loop().time()) > 0:
                await self.sleep(pause)
            response = await self.http.request(
                method, f"{self.base}/{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            try:
                body = json.loads(response.body) if response.body else {}
            except ValueError:
                body = None
            if 200 <= response.status < 300:
                if not isinstance(body, dict):
                    raise NetworkError(SERVICE, "Gmail's answer could not be read.")
                return body
            error = body.get("error") if isinstance(body, dict) else None
            error = error if isinstance(error, dict) else None
            message = str(error.get("message", "")) if error else ""
            details = error.get("errors") if error else None
            reasons = [e.get("reason") for e in details if isinstance(e, dict)] if isinstance(details, list) else []
            transient = response.status in (429, 500, 502, 503, 504) or (
                response.status == 403
                and (
                    any(reason in RATE_LIMITS for reason in reasons)
                    or "rate limit" in message.lower()
                    or "per minute" in message.lower()
                )
            )
            if transient and attempt < RETRIES:
                resume = asyncio.get_running_loop().time() + (1 << attempt)
                self.paused_until = max(self.paused_until, resume)
                continue
            if response.status == 401:
                raise AuthError(SERVICE, "Google rejected the access token.")
            if response.status == 403 and "insufficient authentication scopes" in message:
                raise AuthError(SERVICE, "Gmail did not grant this. Disconnect Gmail and connect it again.")
            raise RemoteError(SERVICE, f"Gmail answered {response.status}: {message or 'no details'}.", response.status)
        raise AssertionError("unreachable")

    async def profile(self, token: str) -> Profile:
        body = await self._call("GET", "profile", token)
        email, history_id = body.get("emailAddress"), body.get("historyId")
        if not isinstance(email, str) or not isinstance(history_id, str):
            raise NetworkError(SERVICE, "Gmail's profile could not be read.")
        return Profile(email, history_id)

    async def inbox_ids(self, token: str) -> list[str]:
        ids: list[str] = []
        page = None
        while True:
            params = {"labelIds": "INBOX", "maxResults": "500", **({"pageToken": page} if page else {})}
            body = await self._call("GET", "messages", token, params=params)
            ids += [m["id"] for m in body.get("messages", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
            page = body.get("nextPageToken")
            if not isinstance(page, str):
                return ids

    async def inbox_changes(self, token: str, history_id: str) -> tuple[list[str], str] | None:
        added: list[str] = []
        page = None
        while True:
            params = {
                "startHistoryId": history_id,
                "labelId": "INBOX",
                "historyTypes": ["messageAdded", "labelAdded"],
                **({"pageToken": page} if page else {}),
            }
            try:
                body = await self._call("GET", "history", token, params=params)
            except RemoteError as error:
                if error.status == 404:
                    return None
                raise
            for record in body.get("history", []):
                for change in [*record.get("messagesAdded", []), *record.get("labelsAdded", [])]:
                    message = change.get("message", {})
                    if "INBOX" in message.get("labelIds", []) and isinstance(message.get("id"), str):
                        added.append(message["id"])
            page = body.get("nextPageToken")
            if not isinstance(page, str):
                return added, str(body.get("historyId", history_id))

    async def _metadata(self, token: str, message_id: str, headers: list[str]) -> dict[str, Any] | None:
        if not is_gmail_id(message_id):
            return None
        try:
            return await self._call(
                "GET", f"messages/{message_id}", token, params={"format": "metadata", "metadataHeaders": headers}
            )
        except RemoteError as error:
            if error.status == 404:
                return None
            raise

    async def messages(self, token: str, ids: list[str], progress: Callable[[int], None]) -> list[GmailMessage]:
        async def read(message_id: str) -> GmailMessage | None:
            raw = await self._metadata(token, message_id, ["Subject", "From"])
            labels = raw.get("labelIds", []) if raw else []
            date = _date(raw.get("internalDate")) if raw else None
            if raw is None or "DRAFT" in labels or "CHAT" in labels or date is None:
                return None
            return GmailMessage(
                raw["id"],
                str(raw.get("threadId", raw["id"])),
                _direction(raw),
                _header(raw, "From"),
                _header(raw, "Subject"),
                date,
            )

        # Reads finish in any order; the messages come back in the order of `ids`.
        pace, pending, tasks, found, done = _Pace(READ_PACE), iter(enumerate(ids)), {}, {}, 0
        try:
            while True:
                while len(tasks) < MAX_IN_FLIGHT and (next_id := next(pending, None)) is not None:
                    await pace.tick()
                    position, message_id = next_id
                    tasks[asyncio.create_task(read(message_id))] = position
                if not tasks:
                    return [found[position] for position in sorted(found)]
                finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                # Take every finished read's error, so none is left unretrieved.
                if errors := [error for task in finished if (error := task.exception()) is not None]:
                    raise errors[0]
                for task in finished:
                    position = tasks.pop(task)
                    if (message := task.result()) is not None:
                        found[position] = message
                    done += 1
                    progress(done)
        finally:
            # On error, stop the reads still in flight.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def original(self, token: str, message_id: str) -> Original:
        raw = await self._metadata(token, message_id, ["From", "To", "Reply-To", "Subject", "Message-ID", "References"])
        if raw is None:
            raise RemoteError(SERVICE, "That email is no longer in Gmail.", 404)
        return Original(
            _direction(raw),
            _header(raw, "From"),
            _header(raw, "To"),
            _header(raw, "Reply-To"),
            _header(raw, "Subject"),
            _header(raw, "Message-ID"),
            _header(raw, "References"),
        )

    async def send(self, token: str, thread_id: str, message: str) -> None:
        raw = base64.urlsafe_b64encode(message.encode()).decode()
        await self._call("POST", "messages/send", token, json={"raw": raw, "threadId": thread_id})

    async def trash_thread(self, token: str, thread_id: str) -> None:
        if not is_gmail_id(thread_id):
            raise RemoteError(SERVICE, "That thread is not a Gmail thread.", 404)
        try:
            await self._call("POST", f"threads/{thread_id}/trash", token)
        except RemoteError as error:
            # A thread that no longer exists counts as trashed.
            if error.status != 404:
                raise

    async def trash_message(self, token: str, message_id: str) -> None:
        if not is_gmail_id(message_id):
            raise RemoteError(SERVICE, "That message is not a Gmail message.", 404)
        try:
            await self._call("POST", f"messages/{message_id}/trash", token)
        except RemoteError as error:
            # A message that no longer exists counts as trashed.
            if error.status != 404:
                raise
