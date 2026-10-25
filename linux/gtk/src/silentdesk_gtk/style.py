"""The app's few style rules, beyond libadwaita's own."""

from __future__ import annotations

from gi.repository import Gdk, Gtk

CSS = """
.reply-entry {
    border-radius: 18px;
    background-color: alpha(currentColor, 0.08);
    padding: 2px 6px;
}
.reply-entry textview,
.reply-entry textview text {
    background: none;
}
"""

_installed = False


def install() -> None:
    """Adds the rules to the display, once."""
    global _installed
    if _installed:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _installed = True
