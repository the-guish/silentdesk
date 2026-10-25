"""The main window: the topic queue, search, Refresh and automatic syncing,
with the topic screen and the Services dialog over it. See
legacy/docs/specs/sync.md."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime

from gi.repository import Adw, Gio, GLib, GObject, Gtk
from silentdesk import api
from silentdesk.contract import Desk, TopicView

from . import format, services, style
from .services_dialog import ServicesDialog
from .topic_list import TopicList
from .topic_page import TopicPage
from .worker import CoreWorker

# Every connected service syncs this often while the app is open, in seconds.
SYNC_EVERY = 120
# Coming back to the window syncs if the last round started this long ago.
SYNC_ON_FOCUS_AFTER = 30
# The header's "Updated … ago" is rewritten this often.
SUBTITLE_EVERY = 30

# Each window action and its keyboard shortcuts. `window.close` is GTK's own.
SHORTCUTS = {
    "win.search": ["<Control>f"],
    "win.refresh": ["<Control>r", "F5"],
    "win.services": ["<Control>comma"],
    "win.show-help-overlay": ["<Control>question"],
    "window.close": ["<Control>w"],
}

# The Keyboard Shortcuts window, as GtkBuilder describes it.
SHORTCUTS_UI = """
<interface>
  <object class="GtkShortcutsWindow" id="shortcuts">
    <property name="modal">True</property>
    <child>
      <object class="GtkShortcutsSection">
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title">Topics</property>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Search</property><property name="accelerator">&lt;Control&gt;f</property>
            </object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Refresh</property><property name="accelerator">&lt;Control&gt;r F5</property>
            </object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Back to the topics</property><property name="accelerator">Escape</property>
            </object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Send a reply</property><property name="accelerator">&lt;Control&gt;Return</property>
            </object></child>
          </object>
        </child>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title">General</property>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Services</property><property name="accelerator">&lt;Control&gt;comma</property>
            </object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Keyboard shortcuts</property>
              <property name="accelerator">&lt;Control&gt;question</property>
            </object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Close the window</property><property name="accelerator">&lt;Control&gt;w</property>
            </object></child>
            <child><object class="GtkShortcutsShortcut">
              <property name="title">Quit</property><property name="accelerator">&lt;Control&gt;q</property>
            </object></child>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>
"""


def version() -> str:
    """The core's version, for the About dialog."""
    return api.version()["version"]


def main_menu() -> Gio.Menu:
    menu = Gio.Menu()
    menu.append("Services", "win.services")
    section = Gio.Menu()
    section.append("Keyboard Shortcuts", "win.show-help-overlay")
    section.append("About SilentDesk", "win.about")
    menu.append_section(None, section)
    return menu


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
        style.install()
        self.desk, self.worker, self.now, self.clock = desk, worker, now, clock
        self.refreshing = False
        self.round_started: float | None = None
        self.last_synced: str | None = None
        self.last_error: str | None = None

        self.topics = TopicList(now)
        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        self.refresh_button.connect("clicked", lambda _: self.refresh())
        self.spinner = Gtk.Spinner()
        self.search_button = Gtk.ToggleButton(icon_name="system-search-symbolic", tooltip_text="Search")
        self.menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic", tooltip_text="Main Menu", menu_model=main_menu(), primary=True
        )
        # When topics last changed, under the app's name.
        self.window_title = Adw.WindowTitle(title="SilentDesk")
        header = Adw.HeaderBar(title_widget=self.window_title)
        header.pack_start(self.search_button)
        header.pack_end(self.menu_button)
        header.pack_end(self.refresh_button)
        header.pack_end(self.spinner)

        # Hidden until the search button, Ctrl+F or typing in the queue opens it.
        self.search = Gtk.SearchEntry(placeholder_text="Search topics", hexpand=True)
        self.search.connect("search-changed", lambda entry: self._search(entry.get_text()))
        self.search_bar = Gtk.SearchBar(child=Adw.Clamp(child=self.search, maximum_size=600))
        self.search_bar.connect_entry(self.search)
        self.search_bar.set_key_capture_widget(self)
        self.search_bar.bind_property(
            "search-mode-enabled",
            self.search_button,
            "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

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

        view = Adw.ToolbarView(content=self.stack)
        view.add_top_bar(header)
        view.add_top_bar(self.search_bar)
        self.topics.view.connect("activate", lambda _, position: self.open_topic(self.topics.at(position)))
        self.navigation = Adw.NavigationView()
        self.navigation.add(Adw.NavigationPage(child=view, title="SilentDesk", tag="queue"))
        # Typing starts a search only on the queue, not on a topic's screen.
        self.navigation.connect("notify::visible-page", lambda *_: self._on_page_changed())
        self.toasts = Adw.ToastOverlay(child=self.navigation)
        self.set_content(self.toasts)
        self.services_dialog: ServicesDialog | None = None
        self.about_dialog: Adw.AboutDialog | None = None

        for name, callback in [
            ("search", self._start_search),
            ("refresh", self.refresh),
            ("services", self.show_services),
            ("about", self.show_about),
        ]:
            action = Gio.SimpleAction(name=name)
            action.connect("activate", lambda _action, _param, callback=callback: callback())
            self.add_action(action)
        for action, accels in SHORTCUTS.items():
            app.set_accels_for_action(action, accels)
        self.set_help_overlay(Gtk.Builder.new_from_string(SHORTCUTS_UI, -1).get_object("shortcuts"))

        self.connect("notify::is-active", lambda *_: self._on_focus())
        self._timers = [
            GLib.timeout_add_seconds(SYNC_EVERY, self._tick),
            GLib.timeout_add_seconds(SUBTITLE_EVERY, self._update_subtitle),
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

    def show_about(self) -> Adw.AboutDialog:
        self.about_dialog = Adw.AboutDialog(
            application_name="SilentDesk",
            application_icon="mail-unread-symbolic",
            developer_name="The SilentDesk Authors",
            version=version(),
            comments="Your work from Gmail, Google Tasks, GitHub, Jira and Slack, in one quiet queue.",
            license_type=Gtk.License.APACHE_2_0,
        )
        self.about_dialog.present(self)
        return self.about_dialog

    def _start_search(self) -> None:
        if self.navigation.get_visible_page().get_tag() == "queue":
            self.search_bar.set_search_mode(True)
            self.search.grab_focus()

    def _on_page_changed(self) -> None:
        on_queue = self.navigation.get_visible_page().get_tag() == "queue"
        self.search_bar.set_key_capture_widget(self if on_queue else None)

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

    def _update_subtitle(self) -> bool:
        if self.refreshing:
            self.window_title.set_subtitle("Refreshing…")
        elif self.last_synced:
            self.window_title.set_subtitle(f"Updated {format.ago(self.last_synced, self.now())}")
        else:
            self.window_title.set_subtitle("")
        return GLib.SOURCE_CONTINUE

    def _show(self) -> None:
        if self.topics.shown:
            page = "list"
        else:
            page = "no-match" if self.topics.total and self.topics.query else "empty"
        self.stack.set_visible_child_name(page)
        self.refresh_button.set_sensitive(not self.refreshing)
        self.spinner.set_spinning(self.refreshing)
        self._update_subtitle()

    def _on_close(self, *_: object) -> bool:
        for timer in self._timers:
            GLib.source_remove(timer)
        self._timers = []
        return False
