"""The queue: a list view of every topic, showing those the core matched."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from gi.repository import Adw, Gio, GObject, Gtk, Pango
from silentdesk.contract import TopicView

from . import format


class TopicObject(GObject.Object):
    """One topic, as the list model holds it."""

    __gtype_name__ = "SilentDeskTopic"

    def __init__(self, topic: TopicView) -> None:
        super().__init__()
        self.topic = topic


class TopicList:
    """A Gtk.ListView over a store of every topic. It shows the topics in
    `matching`, or all of them when it is None. Rebuilding the store costs
    far more than filtering it, so a new search only changes `matching`."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self.now = now
        self.matching: set[str] | None = None
        self.store = Gio.ListStore(item_type=TopicObject)
        self.filter = Gtk.CustomFilter.new(lambda item: self.matching is None or item.topic.id in self.matching)
        self.filtered = Gtk.FilterListModel(model=self.store, filter=self.filter)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup)
        factory.connect("bind", self._bind)
        self.view = Gtk.ListView(
            model=Gtk.NoSelection(model=self.filtered), factory=factory, single_click_activate=True
        )
        self.view.add_css_class("navigation-sidebar")

    def set_topics(self, topics: list[TopicView]) -> None:
        self.store.splice(0, self.store.get_n_items(), [TopicObject(topic) for topic in topics])

    def set_matching(self, topics: list[TopicView] | None) -> None:
        """Shows only `topics`, or every topic when None."""
        self.matching = None if topics is None else {topic.id for topic in topics}
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    @property
    def total(self) -> int:
        return self.store.get_n_items()

    @property
    def shown(self) -> int:
        return self.filtered.get_n_items()

    def at(self, position: int) -> TopicView:
        """The topic shown at `position`."""
        return self.filtered.get_item(position).topic

    def shown_topics(self) -> list[TopicView]:
        return [self.filtered.get_item(i).topic for i in range(self.shown)]

    @staticmethod
    def _setup(factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        avatar = Adw.Avatar(size=36, show_initials=True, valign=Gtk.Align.CENTER)
        title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["dim-label", "caption"])
        date = Gtk.Label(valign=Gtk.Align.CENTER, css_classes=["dim-label", "caption", "numeric"])
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(title)
        text.append(subtitle)
        row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        for widget in (avatar, text, date):
            row.append(widget)
        item.set_child(row)

    def _bind(self, factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        topic = item.get_item().topic
        avatar, text, date = list(_children(item.get_child()))
        title, subtitle = list(_children(text))
        name, icon = format.avatar(topic)
        avatar.set_text(name)
        avatar.set_icon_name(icon)
        title.set_label(topic.title)
        subtitle.set_label(format.subtitle(topic))
        date.set_label(format.short_date(topic.updated_at, self.now()))


def _children(widget: Gtk.Widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()
