from __future__ import annotations

from abc import ABC, abstractmethod


class Clock(ABC):
    @abstractmethod
    def now(self) -> str:
        """The current time in RFC 3339, UTC."""
