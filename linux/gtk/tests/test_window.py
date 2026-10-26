"""The main window against a fake desk. Needs a display: run it under
`xvfb-run` where there is none."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from functools import cache

import pytest
from silentdesk.contract import (
    Desk,
    Direction,
    Item,
    Message,
    Project,
    ServiceStatus,
    StatusCategory,
    SyncFailed,
    TopicQuery,
    TopicStatus,
    TopicView,
    Unsupported,
)

from silentdesk_gtk import filters
from silentdesk_gtk.filters import Choice

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
        self.queries: list[TopicQuery | None] = []
        self.project_list: list[Project] = []

    async def topics(self, query=None):
        # Enough of a query for the window; the core's own tests cover the rest.
        self.queries.append(query)
        query = query or TopicQuery()
        words = query.text.lower().split()
        return [
            t
            for t in self.shown
            if all(w in f"{t.title} {t.items[0].author}".lower() for w in words)
            and (not query.services or t.service in query.services)
            and (not query.people or t.items[0].author in query.people)
        ]

    async def last_synced(self):
        return self.synced

    async def projects(self):
        return sorted(self.project_list, key=lambda p: p.name.casefold())

    async def add_project(self, name):
        self.calls.append(("add_project", name))
        project = Project(f"p{len(self.project_list) + 1}", name.strip())
        self.project_list.append(project)
        return project

    async def rename_project(self, project_id, name):
        self.calls.append(("rename_project", project_id, name))
        self.project_list = [Project(p.id, name) if p.id == project_id else p for p in self.project_list]
        return Project(project_id, name)

    async def delete_project(self, project_id):
        self.calls.append(("delete_project", project_id))
        self.project_list = [p for p in self.project_list if p.id != project_id]
        self.shown = [replace(t, project_id=None) if t.project_id == project_id else t for t in self.shown]

    async def move(self, topic_id, project_id):
        self.calls.append(("move", topic_id, project_id))
        self.shown = [replace(t, project_id=project_id) if t.id == topic_id else t for t in self.shown]

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


def test_every_row_starts_with_a_status_chip_of_one_width(worker):
    desk = FakeDesk()
    review = TopicStatus("Code Review", StatusCategory.IN_PROGRESS)
    desk.shown = [
        replace(topic("j1", "Fix the login timeout", "Bo", "2026-10-24T10:00:00Z", "jira"), status=review),
        replace(topic("j2", "Add the export", "Cy", "2026-10-24T09:00:00Z", "jira"), status=TopicStatus("Open", None)),
        topic("g1", "Invoice for October", "Ana", "2026-10-24T08:00:00Z"),
    ]
    win = window(desk, worker)
    # Laid out on screen, as only a shown window is.
    win.present()
    # The fake desk's sync adds a fourth topic, Lunch?, without a status.
    run_until(lambda: win.topics.shown == 4 and not win.refreshing and win.topics.view.allocated > 0)

    rows = {chip.get_label(): chip for chip in (slot.get_child() for slot in win.topics.slots) if chip.get_mapped()}
    assert set(rows) == {"Code Review", "Open", "—"}
    assert win.topics.chip_width == max(win.topics.chip_widths) > 0
    # Every slot has the chip's width, so every title starts at the same place.
    run_until(lambda: {chip.get_parent().get_width() for chip in rows.values()} == {win.topics.chip_width})
    assert rows["Code Review"].has_css_class("status-in-progress")
    assert rows["—"].has_css_class("status-none"), "a topic without a status gets a dash"

    desk.shown = [topic("g1", "Invoice for October", "Ana", "2026-10-24T08:00:00Z")]
    win.activate_action("win.refresh")
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)
    assert win.topics.chip_width > 0, "the column stays, as wide as the dash"
    assert all(slot.get_visible() for slot in win.topics.slots)
    win.close()


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


def test_the_filter_bar_starts_on_all_and_offers_what_there_is(worker):
    win = window(FakeDesk(), worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)

    bar = win.filter_bar
    assert [f.label for f in bar.filters.values()] == ["Project: All", "Service: All"]
    assert bar.filters["projects"].choices == [Choice("default", "Default")]
    # GitHub is not connected.
    assert bar.filters["services"].choices == [Choice("gmail", "Gmail")]
    assert bar.offered["people"] == [Choice("Bo", "Bo"), Choice("Cy", "Cy")]


def test_filters_and_search_narrow_the_list_together_until_cleared(worker):
    desk = FakeDesk()
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)

    win.filter_bar.filters["services"].click("gmail")
    people = win.filter_bar.add(filters.PEOPLE)
    people.click("Bo")
    run_until(lambda: win.topics.shown == 1)
    assert win.topics.shown_topics()[0].title == "Invoice for October"
    assert people.label == "People: Bo"
    assert desk.queries[-1] == TopicQuery(services=frozenset({"gmail"}), people=frozenset({"Bo"}))

    win.search.set_text("lunch")
    run_until(lambda: win.stack.get_visible_child_name() == "no-match")
    assert desk.queries[-1].text == "lunch"

    win.clear_filters()
    run_until(lambda: win.topics.shown == 1 and win.stack.get_visible_child_name() == "list")
    assert win.topics.shown_topics()[0].title == "Lunch?"
    assert list(win.filter_bar.filters) == ["projects", "services"]
    assert desk.queries[-1] == TopicQuery(text="lunch")


def test_a_service_that_disconnects_leaves_its_filter(worker):
    desk = FakeDesk()
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)
    win.filter_bar.filters["services"].click("gmail")
    run_until(lambda: desk.queries[-1] == TopicQuery(services=frozenset({"gmail"})))

    desk.statuses["gmail"] = ServiceStatus("gmail", True, False, None)
    win.load()

    run_until(lambda: win.filter_bar.filters["services"].label == "Service: All")
    assert win.query == TopicQuery()


def test_a_topic_moves_to_a_new_project_from_its_screen(worker):
    desk = FakeDesk()
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)
    page = win.open_topic(win.topics.at(1))
    picker = page.project
    run_until(lambda: picker.label == "Project: Default")

    picker.search.set_text(" Acme ")
    run_until(lambda: picker.list.get_row_at_index(0).text == 'New Project "Acme"')
    assert picker.list.get_row_at_index(1) is None
    picker.search.emit("activate")

    run_until(lambda: picker.label == "Project: Acme")
    assert desk.calls[-2:] == [("add_project", "Acme"), ("move", "1", "p1")]
    assert win.last_toast == "Moved to Acme"
    # The bar offers the new project once the window reloads.
    run_until(lambda: Choice("p1", "Acme") in win.filter_bar.filters["projects"].choices)


def test_the_projects_dialog_renames_and_deletes_projects(worker):
    desk = FakeDesk()
    desk.project_list = [Project("p1", "Acme")]
    desk.shown[0] = replace(desk.shown[0], project_id="p1")
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)
    dialog = win.show_projects()
    run_until(lambda: len(dialog.rows) == 1)

    dialog.rename("p1", "Beta")
    run_until(lambda: dialog.rows and dialog.rows[0].get_text() == "Beta")
    run_until(lambda: win.filter_bar.filters["projects"].choices[-1] == Choice("p1", "Beta"))

    dialog.delete("p1")
    run_until(lambda: not dialog.rows)
    assert desk.shown[-1].project_id is None
    run_until(lambda: win.filter_bar.filters["projects"].choices == [Choice("default", "Default")])


def test_the_updated_filter_asks_for_a_range_until_removed(worker):
    desk = FakeDesk()
    win = window(desk, worker)
    run_until(lambda: win.topics.shown == 2 and not win.refreshing)

    updated = win.filter_bar.add(filters.UPDATED)
    assert updated.label == "Updated: All"
    updated.set_updated(filters.Updated("within", 7, "days"))

    run_until(lambda: desk.queries[-1] == TopicQuery(updated_from="2026-10-17T12:00:00Z"))
    assert updated.label == "Updated: Last 7 days"
    assert list(win.filter_bar.filters) == ["projects", "services", "updated"]

    win.filter_bar.remove(filters.UPDATED)
    assert list(win.filter_bar.filters) == ["projects", "services"]
    run_until(lambda: win.query == TopicQuery())
