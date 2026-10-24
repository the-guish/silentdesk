"""Topics: units of work the user can act on. Until grouping exists, every
source item gets its own topic."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ....contract import Direction, SyncResult


@dataclass(frozen=True)
class Topic:
    # A UUID, made by SilentDesk.
    id: str
    title: str
    service: str
    # The source item's key within its service.
    item_key: str
    direction: Direction | None
    url: str | None
    # RFC 3339.
    created_at: str
    updated_at: str


def apply(
    topics: Sequence[Topic], service: str, result: SyncResult, now: str, new_id: Callable[[], str]
) -> list[Topic]:
    """The topics after one service's sync: new items get topics, changed
    items update theirs, and gone items lose theirs."""
    raise NotImplementedError


def newest_first(topics: Sequence[Topic]) -> list[Topic]:
    raise NotImplementedError
