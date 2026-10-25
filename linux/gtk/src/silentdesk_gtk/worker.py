"""Runs the core's coroutines on one background thread with one asyncio
loop, and hands their results back to GTK's main loop. GTK must only be
touched from the main thread, and the core's per-service locks only work
within one event loop, so every core call goes through here."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from typing import Any

from gi.repository import GLib

# Gets the result, or the exception the coroutine raised, on the main thread.
Done = Callable[[Any, BaseException | None], None]


class CoreWorker:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="silentdesk-core", daemon=True)
        self.thread.start()

    def run(self, coroutine: Coroutine[Any, Any, Any], done: Done) -> None:
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        # Above idle priority, so results arrive while an animation keeps GTK busy.
        future.add_done_callback(
            lambda finished: GLib.idle_add(self._deliver, finished, done, priority=GLib.PRIORITY_DEFAULT)
        )

    @staticmethod
    def _deliver(future: Future[Any], done: Done) -> bool:
        error = future.exception()
        done(None if error else future.result(), error)
        return GLib.SOURCE_REMOVE

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)
