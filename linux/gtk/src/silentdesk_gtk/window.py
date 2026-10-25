"""The main window: the topic queue, search, Refresh and automatic syncing,
with the topic screen and the Services dialog over it. See
legacy/docs/specs/sync.md."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime

from gi.repository import Adw, GLib, Gtk
from silentdesk.contract import Desk, TopicView

from . import format, services
from .services_dialog import ServicesDialog
from .topic_list import TopicList
from .topic_page import TopicPage
from .worker import CoreWorker

# Every connected service syncs this often while the app is open, in seconds.
SYNC_EVERY = 120
# Coming back to the window syncs if the last round started this long ago.
SYNC_ON_FOCUS_AFTER = 30
# The footer's "Updated … ago" is rewritten this often.
FOOTER_EVERY = 30


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        app: Adw.Application,
        desk: Desk,
        worker: CoreWorker,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(application=app, title="SilentDesk", default_width=960, default_height=640)
        self.desk, self.worker, self.now, self.clock = desk, worker, now, clock
        self.refreshing = False
        self.round_started: float | None = None
        self.last_synced: str | None = None
        self.last_error: str | None = None

        self.topics = TopicList(now)
        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        self.refresh_button.connect("clicked", lambda _: self.refresh())
        self.spinner = Gtk.Spinner()
        services_button = Gtk.Button(icon_name="network-server-symbolic", tooltip_text="Services")
        services_button.connect("clicked", lambda _: self.show_services())
        header = Adw.HeaderBar()
        header.pack_start(services_button)
        header.pack_end(self.refresh_button)
        header.pack_end(self.spinner)

        self.search = Gtk.SearchEntry(placeholder_text="Search topics", hexpand=True)
        self.search.connect("search-changed", lambda entry: self._search(entry.get_text()))
        search_row = Gtk.Box(margin_start=12, margin_end=12, margin_top=6, margin_bottom=6)
        search_row.append(self.search)

        self.stack = Gtk.Stack()
        self.stack.add_named(Gtk.ScrolledWindow(child=self.topics.view, vexpand=True), "list")
        connect_button = Gtk.Button(
            label="Connect a Service", halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"]
        )
        connect_button.connect("clicked", lambda _: self.show_services())
        self.stack.add_named(
            Adw.StatusPage(
                icon_name="mail-unread-symbolic",
                title="No topics yet",
                description="Connect a service, and its work shows up here.",
                child=connect_button,
            ),
            "empty",
        )
        self.stack.add_named(
            Adw.StatusPage(icon_name="system-search-symbolic", title="No topics match your search"), "no-match"
        )

        self.footer = Gtk.Label(
            xalign=0,
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=6,
            css_classes=["dim-label", "caption"],
        )
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(search_row)
        body.append(self.stack)
        view = Adw.ToolbarView(content=body)
        view.add_top_bar(header)
        view.add_bottom_bar(self.footer)
        self.topics.view.connect("activate", lambda _, position: self.open_topic(self.topics.at(position)))
        self.navigation = Adw.NavigationView()
        self.navigation.add(Adw.NavigationPage(child=view, title="SilentDesk", tag="queue"))
        self.toasts = Adw.ToastOverlay(child=self.navigation)
        self.set_content(self.toasts)
        self.services_dialog: ServicesDialog | None = None

        self.connect("notify::is-active", lambda *_: self._on_focus())
        self._timers = [
            GLib.timeout_add_seconds(SYNC_EVERY, self._tick),
            GLib.timeout_add_seconds(FOOTER_EVERY, self._update_footer),
        ]
        self.connect("close-request", self._on_close)
        self._show()
        self.load()
        self.refresh()

    def load(self) -> None:
        """Reads the topics and when they last changed, then shows them."""

        async def read() -> tuple[list[TopicView], str | None]:
            return await self.desk.topics(), await self.desk.last_synced()

        def done(result: tuple[list[TopicView], str | None] | None, error: BaseException | None) -> None:
            if error:
                self._fail(error)
                return
            topics, self.last_synced = result
            self.topics.set_topics(topics)
            self._show()
            self._show_open_topic(topics)

        self.worker.run(read(), done)

    def refresh(self) -> None:
        """Starts a sync round, unless one is running."""
        if self.refreshing:
            return
        self.refreshing = True
        self.round_started = self.clock()
        self._show()

        def done(_: object, error: BaseException | None) -> None:
            self.refreshing = False
            if error:
                self._fail(error)
            self.load()

        self.worker.run(self.desk.sync(), done)

    def open_topic(self, topic: TopicView) -> TopicPage:
        page = TopicPage(
            topic, self.desk, self.worker, self.now, self.toast, self._replied, self._deleted, self._item_deleted
        )
        self.navigation.push(page)
        return page

    def show_services(self) -> ServicesDialog:
        self.services_dialog = ServicesDialog(self.desk, self.worker, self._service_changed)
        self.services_dialog.present(self)
        return self.services_dialog

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def sync_service(self, service: str) -> None:
        """Syncs one service outside the rounds, such as right after it
        connects, then shows the topics."""

        def done(_: object, error: BaseException | None) -> None:
            if error:
                self._fail(error)
            self.load()

        self.worker.run(self.desk.sync(service), done)

    def _service_changed(self, service: str, connected: bool) -> None:
        if connected:
            self.sync_service(service)
        else:
            self.load()

    def _replied(self, topic: TopicView) -> None:
        self.sync_service(topic.service)

    def _deleted(self, topic: TopicView) -> None:
        self.navigation.pop_to_tag("queue")
        self.toast(services.deletion(topic.service, "topic").done)
        self.load()

    def _item_deleted(self, topic: TopicView) -> None:
        self.toast(services.deletion(topic.service, "item").done)
        self.load()

    def _show_open_topic(self, topics: list[TopicView]) -> None:
        """Brings the open topic screen up to date, or closes it when its
        topic is gone."""
        page = self.navigation.get_visible_page()
        if not isinstance(page, TopicPage):
            return
        current = next((topic for topic in topics if topic.id == page.topic.id), None)
        if current is None:
            self.navigation.pop_to_tag("queue")
        else:
            page.show_topic(current)

    def _tick(self) -> bool:
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def _on_focus(self) -> None:
        if self.is_active() and (self.round_started is None or self.clock() - self.round_started > SYNC_ON_FOCUS_AFTER):
            self.refresh()

    def _search(self, query: str) -> None:
        self.topics.set_query(query)
        self._show()

    def _fail(self, error: BaseException) -> None:
        self.last_error = format.describe(error)
        print(self.last_error, file=sys.stderr)
        self.toasts.add_toast(Adw.Toast(title=self.last_error, timeout=6))
        self._show()

    def _update_footer(self) -> bool:
        if self.refreshing:
            self.footer.set_label("Refreshing…")
        elif self.last_synced:
            self.footer.set_label(f"Updated {format.ago(self.last_synced, self.now())}")
        else:
            self.footer.set_label("")
        return GLib.SOURCE_CONTINUE

    def _show(self) -> None:
        if self.topics.shown:
            page = "list"
        else:
            page = "no-match" if self.topics.total and self.topics.query else "empty"
        self.stack.set_visible_child_name(page)
        self.refresh_button.set_sensitive(not self.refreshing)
        self.spinner.set_spinning(self.refreshing)
        self._update_footer()

    def _on_close(self, *_: object) -> bool:
        for timer in self._timers:
            GLib.source_remove(timer)
        self._timers = []
        return False
