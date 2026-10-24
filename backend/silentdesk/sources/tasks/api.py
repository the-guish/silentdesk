"""Google Tasks REST calls, read-only."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from ...adapters.http import send
from ...core import errors
from ..gmail import wire
from ..gmail.oauth import Grant

BASE = "https://tasks.googleapis.com/tasks/v1"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
SERVICE = "Google Tasks"

# Read-only access to task lists and tasks. `openid email` only names the
# account in Settings.
GRANT = Grant(
    service=SERVICE,
    scopes=("https://www.googleapis.com/auth/tasks.readonly", "openid", "email"),
    required=("https://www.googleapis.com/auth/tasks.readonly",),
)

# Stop paging after this many pages (100 items each), per list.
MAX_PAGES = 20


@dataclass
class TaskMeta:
    task_id: str
    list_id: str
    list_title: str
    title: str
    # `YYYY-MM-DD`; Google keeps the day only.
    due: str | None
    # Where the task came from, when Google says: Gmail, Docs or Chat.
    origin: str | None
    url: str
    # RFC 3339, when the task was last updated.
    date: str


@dataclass
class Page:
    items: list[Any]
    next_page_token: str | None


def _page(parse_item: Callable[[Any], Any]) -> Callable[[Any], Page]:
    def parse(value: Any) -> Page:
        o = wire.obj(value)
        return Page(wire.items(o, "items", parse_item), wire.opt_string(o, "nextPageToken"))

    return parse


@dataclass
class RawList:
    id: str
    title: str


def raw_list(value: Any) -> RawList:
    o = wire.obj(value)
    return RawList(wire.string(o, "id"), wire.string(o, "title", ""))


@dataclass
class RawTask:
    id: str
    title: str
    status: str
    due: str | None
    updated: str
    web_view_link: str | None
    # The `type` of each link.
    links: list[str]
    # `assignmentInfo.surfaceType`, when the task was assigned from
    # elsewhere.
    surface_type: str | None
    deleted: bool


def _link_kind(value: Any) -> str:
    return wire.string(wire.obj(value), "type", "")


def raw_task(value: Any) -> RawTask:
    o = wire.obj(value)
    assignment = o.get("assignmentInfo")
    surface_type = None if assignment is None else wire.opt_string(wire.obj(assignment), "surfaceType")
    return RawTask(
        id=wire.string(o, "id"),
        title=wire.string(o, "title", ""),
        status=wire.string(o, "status", ""),
        due=wire.opt_string(o, "due"),
        updated=wire.string(o, "updated", ""),
        web_view_link=wire.opt_string(o, "webViewLink"),
        links=wire.items(o, "links", _link_kind),
        surface_type=surface_type,
        deleted=wire.boolean(o, "deleted"),
    )


def _error_message(response: httpx.Response) -> str | None:
    try:
        error = wire.obj(response.json()).get("error")
        return None if error is None else wire.string(wire.obj(error), "message")
    except (ValueError, wire.Malformed):
        return None


async def _get[T](
    http: httpx.AsyncClient,
    token: str,
    url: str,
    query: list[tuple[str, str]],
    parse: Callable[[Any], T],
) -> T:
    response = await send(http, "GET", url, headers={"Authorization": f"Bearer {token}"}, params=query)
    status = response.status_code
    if response.is_success:
        return wire.read_json(response, parse)
    if status == 401:
        raise errors.Reauthorize(SERVICE)
    message = _error_message(response)
    if message is None:
        message = httpx.codes.get_reason_phrase(status) or "unknown error"
    raise errors.Api(SERVICE, status, message)


# What the `url` crate leaves as is in a path segment; everything else is
# percent-encoded.
_SEGMENT_SAFE = "!$&'()*+,:;=@[]^|"


def endpoint(segments: list[str]) -> str:
    """`BASE` plus path segments, each percent-encoded."""
    return BASE + "".join("/" + quote(s, safe=_SEGMENT_SAFE) for s in segments)


async def _all[T](
    http: httpx.AsyncClient,
    token: str,
    url: str,
    query: list[tuple[str, str]],
    parse_item: Callable[[Any], T],
) -> list[T]:
    """Every page of a list endpoint, up to `MAX_PAGES`."""
    items: list[T] = []
    page_token: str | None = None
    for _ in range(MAX_PAGES):
        q = list(query)
        if page_token is not None:
            q.append(("pageToken", page_token))
        page = await _get(http, token, url, q, _page(parse_item))
        items.extend(page.items)
        page_token = page.next_page_token
        if page_token is None:
            break
    return items


async def email(http: httpx.AsyncClient, token: str) -> str:
    return await _get(http, token, USERINFO, [], lambda v: wire.string(wire.obj(v), "email"))


async def open_tasks(http: httpx.AsyncClient, token: str) -> list[TaskMeta]:
    """Every open task in every list, including tasks assigned to the user
    from Docs or Chat, most recently updated first."""
    lists = await _all(http, token, endpoint(["users", "@me", "lists"]), [("maxResults", "100")], raw_list)
    out: list[TaskMeta] = []
    for lst in lists:
        tasks = await _all(
            http,
            token,
            endpoint(["lists", lst.id, "tasks"]),
            [
                ("maxResults", "100"),
                ("showCompleted", "false"),
                ("showHidden", "false"),
                ("showDeleted", "false"),
                ("showAssigned", "true"),
            ],
            raw_task,
        )
        out.extend(m for t in tasks if (m := to_meta(t, lst.id, lst.title)) is not None)
    # Stable, like Rust's `sort_by`.
    out.sort(key=lambda m: m.date, reverse=True)
    return out


_SURFACES = {"DOCUMENT": "Docs", "SPACE": "Chat", "GMAIL": "Gmail"}
_LINKS = {"email": "Gmail", "chat_message": "Chat"}


def _day(due: str | None) -> str | None:
    """The first 10 bytes of `due`, when there are that many and they end on
    a character boundary."""
    if due is None:
        return None
    head = due.encode()[:10]
    if len(head) != 10:
        return None
    try:
        return head.decode()
    except UnicodeDecodeError:
        return None


def to_meta(task: RawTask, list_id: str, list_title: str) -> TaskMeta | None:
    if task.deleted or task.status == "completed":
        return None
    origin = _SURFACES.get(task.surface_type) if task.surface_type is not None else None
    if origin is None:
        origin = next((_LINKS[k] for k in task.links if k in _LINKS), None)
    return TaskMeta(
        task_id=task.id,
        list_id=list_id,
        list_title=list_title,
        title=task.title.strip(),
        due=_day(task.due),
        origin=origin,
        url=task.web_view_link if task.web_view_link is not None else "https://tasks.google.com/",
        date=task.updated,
    )
