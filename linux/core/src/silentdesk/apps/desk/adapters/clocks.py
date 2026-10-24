from __future__ import annotations

from datetime import UTC, datetime

from ..ports.clock import Clock


class SystemClock(Clock):
    def now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class FixedClock(Clock):
    """Always the same time, for repeatable tests (`--now`)."""

    def __init__(self, now: str) -> None:
        self.fixed = now

    def now(self) -> str:
        return self.fixed
