"""What the Google app remembers between syncs, per service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoogleState:
    # The connected account.
    email: str
    # Where Gmail's next sync starts. None for Google Tasks, and before Gmail's first full sync.
    history_id: str | None
