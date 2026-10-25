"""The main window against a fake desk. Needs a display: run it under
`xvfb-run` where there is none."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from functools import cache

import pytest
from silentdesk.contract import Desk, Direction, Item, Message, ServiceStatus, SyncFailed, TopicView, Unsupported

# Through the app's package, which picks the GTK and libadwaita versions first.
from silentdesk_gtk.window import MainWindow
from silentdesk_gtk.worker import CoreWorker

from gi.repository import Adw, Gio, GLib  # isort: skip


def topic(id: str, title: str, author: str, date: str, service: str = "gmail") -> TopicView:
    # Gmail's topics and items are deletable; the others' are not.
    deletable = service == "gmail"
    return TopicView(id, service, title, [Item(id, Direction.INBOUND, author, None, date, deletable)], date, deletable)


def thread(id: str, *keys: str) -> TopicView:
    """A Gmail thread with several messages."""
    items = [Item(key, Direction.INBOUND, "Bo", None, f"2026-10-24T0{n}:00:00Z", True) for n, key in enumerate(keys)]
    return TopicView(id, "gmail", "Thread", items, items[-1].date, True)


class FakeDesk(Desk):
    def __init__(self, sync_error: Exception | None = None) -> None:
        self.shown = [topic("1", "Invoice for October", "Bo", "2026-10-24T09:00:00Z")]
        self.synced: str | None = None
        self.syncs = 0
        self.sync_error = sync_error
        self.statuses = {
            "github": ServiceStatus("github", True, False, None),
            "gmail": ServiceStatus("gmail", True, True, "ana@example.com"),
        }
        self.calls: list[tuple] = []

    async def topics(self, query=None):
        # Search only; the core's own tests cover the rest of a query.
        words = query.text.lower().split() if query else []
        return [t for t in self.shown if all(w in f"{t.title} {t.items[0].author}".lower() for w in words)]

    async def last_synced(self):
        return self.synced

    # The window has no projects yet.
    async def projects(self):
        return []

    async def add_project(self, name):
        raise NotImplementedError

    async def rename_project(self, project_id, name):
        raise NotImplementedError

    async def delete_project(self, project_id):
        raise NotImplementedError

    async def move(self, topic_id, project_id):
        raise NotImplementedError

    async def sync(self, service=None):
        if service:
            self.calls.append(("sync", service))
            return
        self.syncs += 1
        if self.sync_error:
            raise self.sync_error
        self.shown.insert(0, topic("2", "Lunch?", "Cy", "2026-10-24T11:00:00Z"))
        self.synced = "2026-10-24T11:58:00Z"

    async def services(self):
        return list(self.statuses.values())

    async def connect(self, service, params):
        self.calls.append(("connect", service, dict(params)))
        self.statuses[service] = ServiceStatus(service, True, True, "ana")
        return self.statuses[service]

    async def disconnect(self, service):
        self.calls.append(("disconnect", service))
        self.statuses[service] = ServiceStatus(service, True, False, None)
        self.shown = [t for t in self.shown if t.service != service]
        return self.statuses[service]

    async def history(self, topic_id):
        if topic_id != "slack-1":
            raise Unsupported("gmail", "SilentDesk shows Gmail's headers only.")
        return [
            Message("10.0", Direction.INBOUND, "Bo", "Can you check prod?", "2026-10-24T10:00:00Z"),
            Message("20.0", Direction.OUTBOUND, "Ana", "On it.", "2026-10-24T10:05:00Z"),
        ]

    async def reply(self, topic_id, body):
        self.calls.append(("reply", topic_id, body))

    async def delete_item(self, topic_id, item_key):
        self.calls.append(("delete", topic_id, item_key))
        [old] = [t for t in self.shown if t.id == topic_id]
        items = [item for item in old.items if item.key != item_key]
        # Titled from its first item, as Gmail titles a thread.
        new = replace(old, title=f"From {items[0].key}", items=items, updated_at=items[-1].date)
        self.shown = [new if t.id == topic_id else t for t in self.shown]

    async def delete(self, topic_id):
        self.calls.append(("delete", topic_id))
        self.shown = [t for t in self.shown if t.id != topic_id]


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


@cache
def application() -> Adw.Application:
    """One application for every test. Windows join an application only after
    its startup, which registering runs, and an application registers on the
    session bus once per process."""
    app = Adw.Application(application_id="com.silentdesk.test", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    return app


def window(desk: FakeDesk, worker: CoreWorker) -> MainWindow:
    return MainWindow(application(), desk, worker, now=lambda: datetime(2026, 10, 24, 12, 0, tzinfo=UTC))


def test_the_window_syncs_on_start_and_shows_the_topics(worker):
    desk = FakeDesk()
    win = window(desk, worker)

    run_until(lambda: win.topics.shown == 2 and not win.refreshing)

    assert win.props.maximized
    assert desk.syncs == 1
    assert [t.title for t in win.topics.shown_topics()] == ["Lunch?", "Invoice for October"]
    assert win.stack.get_visible_child_name() == "list"
    assert win.window_title.get_subtitle() == "Updated 2 min ago"


def test_search_narrows_the_list(worker):
    win = window(FakeDesk(), worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)

    win.search.set_text("cy")
    run_until(lambda: win.topics.shown == 1)
    assert win.topics.shown_topics()[0].title == "Lunch?"

    win.search.set_text("nothing like this")
    run_until(lambda: win.stack.get_visible_child_name() == "no-match")


def test_a_failed_round_is_reported_and_the_old_topics_stay(worker):
    from silentdesk.contract import AuthError

    desk = FakeDesk(SyncFailed([("gmail", AuthError("gmail", "Expired."))]))
    win = window(desk, worker)

    run_until(lambda: win.last_error is not None and not win.refreshing and win.topics.shown == 1)
    assert win.last_error == "Could not sync Gmail: Expired."


def test_refresh_does_not_start_a_second_round_while_one_runs(worker):
    desk = FakeDesk()
    win = window(desk, worker)
    win.refresh()
    win.refresh()
    run_until(lambda: not win.refreshing)
    assert desk.syncs == 1


def started(desk: FakeDesk, worker: CoreWorker) -> MainWindow:
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)
    return win


def test_a_topic_without_a_conversation_shows_its_items_and_a_reply_box(worker):
    win = started(FakeDesk(), worker)

    page = win.open_topic(win.topics.at(1))
    run_until(lambda: not page.loading)

    assert page.showing == "items"
    assert page.entries == [("Bo", "Received · Today 09:00", "")]
    assert page.note.get_visible()
    assert page.reply_view is not None and page.delete_button.get_visible()
    assert win.navigation.get_visible_page() is page


def test_a_slack_topic_shows_its_conversation_and_offers_no_reply(worker):
    desk = FakeDesk()
    desk.shown.append(topic("slack-1", "Bo", "Bo", "2026-10-24T10:00:00Z", service="slack"))
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 3 and not win.refreshing)

    page = win.open_topic(next(t for t in win.topics.shown_topics() if t.service == "slack"))
    run_until(lambda: page.showing == "history")

    assert page.entries == [
        ("Bo", "Received · Today 10:00", "Can you check prod?"),
        ("Ana", "Sent · Today 10:05", "On it."),
    ]
    assert not page.note.get_visible()
    assert page.reply_view is None and not page.delete_button.get_visible()


def test_a_reply_is_sent_then_its_service_syncs(worker):
    desk = FakeDesk()
    win = started(desk, worker)
    page = win.open_topic(win.topics.at(1))
    page.send()
    assert desk.calls == []

    page.reply_view.get_buffer().set_text("Paid, thanks.")
    assert page.send_button.get_sensitive()
    page.send()

    run_until(lambda: ("sync", "gmail") in desk.calls)
    assert desk.calls[0] == ("reply", "1", "Paid, thanks.")
    buffer = page.reply_view.get_buffer()
    assert buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False) == ""


def test_a_deleted_topic_leaves_the_queue(worker):
    desk = FakeDesk()
    win = started(desk, worker)
    page = win.open_topic(win.topics.at(1))

    page.delete()

    run_until(lambda: win.topics.shown == 1)
    assert desk.calls == [("delete", "1")]
    assert win.navigation.get_visible_page().get_tag() == "queue"


def test_connecting_a_service_asks_for_its_fields_then_syncs_it(worker):
    desk = FakeDesk()
    win = started(desk, worker)
    dialog = win.show_services()
    run_until(lambda: len(dialog.rows) == 2)

    dialog.connect_service("github", {"token": "", "server": ""})
    assert dialog.last_error == "Fill in: Personal access token."

    dialog.connect_service("github", {"token": " ghp_1 ", "server": ""})
    run_until(lambda: ("sync", "github") in desk.calls)
    assert desk.calls[0] == ("connect", "github", {"token": "ghp_1"})
    run_until(lambda: dialog.statuses and dialog.statuses[0].connected)


def test_disconnecting_a_service_drops_its_topics(worker):
    desk = FakeDesk()
    win = started(desk, worker)
    dialog = win.show_services()
    run_until(lambda: len(dialog.rows) == 2)

    dialog.disconnect_service("gmail")

    run_until(lambda: win.topics.shown == 0)
    assert desk.calls == [("disconnect", "gmail")]
    assert win.stack.get_visible_child_name() == "empty"


def test_each_deletable_item_of_a_thread_can_be_deleted_on_its_own(worker):
    desk = FakeDesk()
    desk.shown.append(thread("t", "m1", "m2"))
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 3 and not win.refreshing)
    page = win.open_topic(next(t for t in win.topics.shown_topics() if t.id == "t"))
    assert sorted(page.item_buttons) == ["m1", "m2"]

    page.delete_item("m1")

    run_until(lambda: desk.calls == [("delete", "t", "m1")] and len(page.entries) == 1)
    # As the core reports it after the deletion: Gmail retitles a thread.
    assert [item.key for item in page.topic.items] == ["m2"]
    assert page.window_title.get_title() == "From m2"
    # One item left: the header's button deletes it, with the topic.
    assert page.item_buttons == {}
    assert win.navigation.get_visible_page() is page


def test_a_topic_that_is_not_deletable_offers_no_delete(worker):
    win = started(FakeDesk(), worker)
    page = win.open_topic(topic("9", "PR", "Cy", "2026-10-24T10:00:00Z", service="github"))
    assert not page.delete_button.get_visible() and page.item_buttons == {}


def test_search_stays_hidden_until_asked_for_and_only_on_the_queue(worker):
    win = started(FakeDesk(), worker)
    assert not win.search_bar.get_search_mode()

    win.activate_action("win.search")
    assert win.search_bar.get_search_mode() and win.search_button.get_active()

    win.search_bar.set_search_mode(False)
    page = win.open_topic(win.topics.at(0))
    run_until(lambda: win.navigation.get_visible_page() is page)
    win.activate_action("win.search")
    assert not win.search_bar.get_search_mode()


def test_the_main_actions_have_their_usual_shortcuts(worker):
    win = started(FakeDesk(), worker)
    app = win.get_application()
    assert app.get_accels_for_action("win.search") == ["<Control>f"]
    assert app.get_accels_for_action("win.refresh") == ["<Control>r", "F5"]
    assert app.get_accels_for_action("win.services") == ["<Control>comma"]
    assert app.get_accels_for_action("win.show-help-overlay") == ["<Control>question"]
    assert win.get_help_overlay() is not None


def test_about_names_the_app_and_its_license(worker):
    from gi.repository import Gtk

    win = started(FakeDesk(), worker)
    win.activate_action("win.about")
    assert win.about_dialog.get_application_name() == "SilentDesk"
    assert win.about_dialog.get_license_type() == Gtk.License.APACHE_2_0


def test_the_services_action_opens_the_services_dialog(worker):
    win = started(FakeDesk(), worker)
    win.activate_action("win.services")
    assert win.services_dialog is not None
