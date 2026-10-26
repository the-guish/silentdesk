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
/* A topic's status, first in its row (docs/specs/topic-status.md). */
.status-chip {
    border-radius: 999px;
    padding: 6px 10px;
    font-weight: bold;
    background-color: alpha(currentColor, 0.1);
}
.status-chip.status-in-progress {
    background-color: alpha(@blue_3, 0.3);
}
.status-chip.status-done {
    background-color: alpha(@green_4, 0.3);
}
.status-chip.status-none {
    background-color: alpha(currentColor, 0.05);
    color: alpha(currentColor, 0.55);
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
