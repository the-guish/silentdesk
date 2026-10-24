"""The application and its main window."""

from __future__ import annotations

import sys

import gi
from silentdesk import api

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

APP_ID = "com.silentdesk.app"


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="SilentDesk", default_width=960, default_height=640)
        core = api.version()

        page = Adw.StatusPage(
            icon_name="mail-unread-symbolic",
            title="No topics yet",
            description=f"Topics will show here.\nCore {core['version']}, contract {core['contract']}.",
        )
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar(title_widget=Gtk.Label(label="SilentDesk", css_classes=["title"])))
        self.set_content(view)


def main() -> int:
    app = Adw.Application(application_id=APP_ID)
    app.connect("activate", lambda app: Window(app).present())
    return app.run(sys.argv)
