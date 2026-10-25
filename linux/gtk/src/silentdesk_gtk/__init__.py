"""SilentDesk's GTK app. It reaches the core through `silentdesk.api`, and
uses `silentdesk.contract` for the core's types."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
