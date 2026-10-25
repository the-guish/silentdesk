"""The main window against a fake desk. Needs a display: run it under
`xvfb-run` where there is none."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from silentdesk.contract import Desk, Direction, Item, ServiceStatus, SyncFailed, TopicView

# Through the app's package, which picks the GTK and libadwaita versions first.
from silentdesk_gtk.window import MainWindow, describe
from silentdesk_gtk.worker import CoreWorker

from gi.repository import Adw, GLib  # isort: skip


def topic(id: str, title: str, author: str, date: str) -> TopicView:
    return TopicView(id, "gmail", title, [Item(id, Direction.INBOUND, author, None, date)], date)


class FakeDesk(Desk):
    def __init__(self, sync_error: Exception | None = None) -> None:
        self.shown = [topic("1", "Invoice for October", "Bo", "2026-10-24T09:00:00Z")]
        self.synced: str | None = None
        self.syncs = 0
        self.sync_error = sync_error

    async def topics(self):
        return list(self.shown)

    async def last_synced(self):
        return self.synced

    async def sync(self, service=None):
        self.syncs += 1
        if self.sync_error:
            raise self.sync_error
        self.shown.insert(0, topic("2", "Lunch?", "Cy", "2026-10-24T11:00:00Z"))
        self.synced = "2026-10-24T11:58:00Z"

    async def services(self):
        return [ServiceStatus("gmail", True, True, "ana@example.com")]

    async def connect(self, service, params):
        raise NotImplementedError

    async def disconnect(self, service):
        raise NotImplementedError

    async def history(self, topic_id):
        raise NotImplementedError

    async def reply(self, topic_id, body):
        raise NotImplementedError

    async def delete(self, topic_id):
        raise NotImplementedError


def run_until(condition, seconds: float = 5) -> None:
    """Runs GTK's main loop until `condition` holds."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        context.iteration(False)
        time.sleep(0.005)


@pytest.fixture
def worker():
    Adw.init()
    worker = CoreWorker()
    yield worker
    worker.stop()


def window(desk: FakeDesk, worker: CoreWorker) -> MainWindow:
    app = Adw.Application(application_id="com.silentdesk.test")
    return MainWindow(app, desk, worker, now=lambda: datetime(2026, 10, 24, 12, 0, tzinfo=UTC))


def test_the_window_syncs_on_start_and_shows_the_topics(worker):
    desk = FakeDesk()
    win = window(desk, worker)

    run_until(lambda: win.topics.total == 2 and not win.refreshing)

    assert desk.syncs == 1
    assert [t.title for t in win.topics.shown_topics()] == ["Lunch?", "Invoice for October"]
    assert win.stack.get_visible_child_name() == "list"
    assert win.footer.get_label() == "Updated 2 min ago"


def test_search_narrows_the_list(worker):
    win = window(FakeDesk(), worker)
    run_until(lambda: win.topics.total == 2 and not win.refreshing)

    win.search.set_text("cy")
    run_until(lambda: win.topics.shown == 1)
    assert win.topics.shown_topics()[0].title == "Lunch?"

    win.search.set_text("nothing like this")
    run_until(lambda: win.stack.get_visible_child_name() == "no-match")


def test_a_failed_round_is_reported_and_the_old_topics_stay(worker):
    from silentdesk.contract import AuthError

    desk = FakeDesk(SyncFailed([("gmail", AuthError("gmail", "Expired."))]))
    win = window(desk, worker)

    run_until(lambda: win.last_error is not None and not win.refreshing and win.topics.total == 1)
    assert win.last_error == "Could not sync Gmail."


def test_refresh_does_not_start_a_second_round_while_one_runs(worker):
    desk = FakeDesk()
    win = window(desk, worker)
    win.refresh()
    win.refresh()
    run_until(lambda: not win.refreshing)
    assert desk.syncs == 1


def test_errors_read_as_one_line():
    from silentdesk.contract import RemoteError

    assert describe(RemoteError("jira", "Jira answered 503.")) == "Jira: Jira answered 503."
    assert describe(ValueError("Bad.")) == "Bad."
