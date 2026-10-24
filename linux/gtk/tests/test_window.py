"""Builds the main window, so CI catches broken widget code. Needs a display:
run it under `xvfb-run` where there is none."""

from silentdesk import api

# Through the app module, which picks the GTK and libadwaita versions first.
from silentdesk_gtk.app import Adw, Window


def test_window_shows_the_core_version():
    Adw.init()
    window = Window(Adw.Application(application_id="com.silentdesk.test"))
    page = window.get_content().get_content()
    assert page.get_title() == "No topics yet"
    assert f"Core {api.version()['version']}" in page.get_description()
