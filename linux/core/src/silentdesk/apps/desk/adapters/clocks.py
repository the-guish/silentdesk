from __future__ import annotations

from ..ports.clock import Clock


class SystemClock(Clock):
    def now(self) -> str:
        raise NotImplementedError


class FixedClock(Clock):
    """Always the same time, for repeatable tests (`--now`)."""

    def __init__(self, now: str) -> None:
        self.fixed = now

    def now(self) -> str:
        raise NotImplementedError
