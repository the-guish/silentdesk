"""Google Tasks, as far as SilentDesk needs them. Notes are never kept."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Grant:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class TaskList:
    list_id: str
    title: str


@dataclass(frozen=True)
class GoogleTask:
    task_id: str
    list_id: str
    list_title: str
    title: str
    completed: bool
    deleted: bool
    # YYYY-MM-DD: Google keeps the day only.
    due: str | None
    # Where the task came from: "Gmail", "Docs" or "Chat".
    origin: str | None
    url: str
    # RFC 3339.
    updated: str
