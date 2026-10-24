"""The application: every source, the Topics list and automatic syncing,
behind one table of methods the UI calls through Rust."""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import httpx

from .core import errors
from .core.model import to_json
from .core.ports import Host
from .core.topics import now_rfc3339, topic_views
from .sources.base import Method, Source
from .sources.github.service import GitHubSource
from .sources.gmail.service import GmailSource
from .sources.jira.service import JiraSource
from .sources.slack.service import SlackSource
from .sources.tasks.service import TasksSource

# Rounds run every INTERVAL seconds; focus syncs wait at least MIN_GAP after
# the last round started.
INTERVAL = 120.0
MIN_GAP = 30.0


class AutoSync:
    """Syncs every connected source at startup, every two minutes, and when
    the window comes back into focus. It works quietly: results reach the UI
    as events, never as notifications (core principle 6). See
    docs/specs/sync.md."""

    def __init__(self, host: Host, sources: list[Source]):
        self.host = host
        # Gmail goes last: its first sync can take minutes.
        self.sources = sources
        self.wake = asyncio.Event()
        self.running = False
        self.started: float | None = None
        # RFC 3339, when the last round finished.
        self.finished: str | None = None

    async def run(self) -> None:
        """Runs for the life of the process."""
        while True:
            self.started = time.monotonic()
            self._set_running(True)
            await self.round()
            self.finished = now_rfc3339()
            self._set_running(False)
            try:
                await asyncio.wait_for(self.wake.wait(), INTERVAL)
            except TimeoutError:
                pass
            self.wake.clear()

    def _set_running(self, running: bool) -> None:
        self.running = running
        self.host.events.emit("sync-round", {"running": running})

    async def round(self) -> None:
        """Each connected source in turn, skipping any that is busy."""
        for source in self.sources:
            if source.op.locked():
                continue
            async with source.op:
                try:
                    await source.sync()
                    error = None
                except (errors.NotConnected, errors.NotConfigured):
                    # Nothing to sync.
                    continue
                except errors.AppError as e:
                    error = e.message
                except Exception as e:  # noqa: BLE001 - one source must not stop the round
                    print(f"silentdesk: {source.name} sync failed: {e!r}", file=sys.stderr)
                    error = "Something went wrong. See the log for details."
            if error is None:
                self.host.events.emit("topics-updated", {"at": now_rfc3339()})
            self.host.events.emit("sync-finished", {"service": source.name, "error": error})

    def soon(self) -> None:
        """Asks for a round now, unless one started less than MIN_GAP ago."""
        if self.started is None or time.monotonic() - self.started >= MIN_GAP:
            self.wake.set()

    def refresh(self) -> None:
        """Starts a round now, unless one is running."""
        if not self.running:
            self.wake.set()


class App:
    def __init__(self, host: Host, http: httpx.AsyncClient):
        self.host = host
        self.sources: list[Source] = [
            TasksSource(host, http),
            GitHubSource(host, http),
            JiraSource(host, http),
            SlackSource(host, http),
            GmailSource(host, http),
        ]
        self.auto_sync = AutoSync(host, self.sources)
        self.methods: dict[str, Method] = {
            "topics.list": self._list_topics,
            "sync.soon": self._sync_soon,
            "sync.refresh": self._refresh,
            "sync.running": self._sync_running,
            "sync.lastSynced": self._last_synced,
        }
        for source in self.sources:
            self.methods.update(source.methods())

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        fn = self.methods.get(method)
        if fn is None:
            raise errors.AppError(f"Unknown method: {method}")
        return to_json(await fn(params))

    async def _list_topics(self, _: dict[str, Any]) -> list[dict[str, Any]]:
        return topic_views(await self.host.store.read())

    async def _sync_soon(self, _: dict[str, Any]) -> None:
        self.auto_sync.soon()

    async def _refresh(self, _: dict[str, Any]) -> None:
        self.auto_sync.refresh()

    async def _sync_running(self, _: dict[str, Any]) -> bool:
        return self.auto_sync.running

    async def _last_synced(self, _: dict[str, Any]) -> str | None:
        return self.auto_sync.finished
