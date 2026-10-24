"""The user's browser, for sign-in pages."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Browser(ABC):
    @abstractmethod
    async def open(self, url: str) -> None:
        """Opens an https URL."""
