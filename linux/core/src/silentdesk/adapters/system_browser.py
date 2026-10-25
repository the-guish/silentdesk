"""The user's default browser, and a stand-in for tests."""

from __future__ import annotations

import asyncio
import webbrowser
from urllib.parse import urlsplit

from ..contract import Browser, Http


class SystemBrowser(Browser):
    async def open(self, url: str) -> None:
        if urlsplit(url).scheme != "https":
            raise ValueError(f"Only https pages are opened: {url}")
        if not await asyncio.to_thread(webbrowser.open, url):
            raise OSError("No web browser could be opened.")


class FollowingBrowser(Browser):
    """For tests only (SILENTDESK_TEST_BROWSER=follow): fetches the page and
    follows its redirects, as a browser would after the user signs in."""

    def __init__(self, http: Http) -> None:
        self.http = http

    async def open(self, url: str) -> None:
        await self.http.request("GET", url)
