"""What the Gmail app remembers between syncs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GmailState:
    # The connected account.
    email: str
    # Where the next sync starts. None before the first full sync.
    history_id: str | None
