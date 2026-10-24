"""What the Google Tasks app remembers between syncs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoogleState:
    # The connected account.
    email: str
