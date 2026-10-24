"""The user's default browser."""

from __future__ import annotations

from ..contract import Browser


class SystemBrowser(Browser):
    async def open(self, url: str) -> None:
        raise NotImplementedError
