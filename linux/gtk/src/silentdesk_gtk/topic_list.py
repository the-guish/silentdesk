"""The queue: a list view of every topic, showing those the core matched."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango
from silentdesk.contract import TopicView

from . import format


class TopicObject(GObject.Object):
    """One topic, as the list model holds it."""

    __gtype_name__ = "SilentDeskTopic"

    def __init__(self, topic: TopicView) -> None:
        super().__init__()
        self.topic = topic


class QueueView(Gtk.ListView):
    """The list view, which says when its width changes."""

    def __init__(self, on_width: Callable[[int], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self.on_width = on_width
        self.allocated = 0

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        Gtk.ListView.do_size_allocate(self, width, height, baseline)
        if width != self.allocated:
            self.allocated = width
            # Resizing the chips during this allocation would start another.
            GLib.idle_add(self.on_width, width)


class TopicList:
    """A Gtk.ListView over a store of every topic. It shows the topics in
    `matching`, or all of them when it is None. Rebuilding the store costs
    far more than filtering it, so a new search only changes `matching`.

    Every row starts with its topic's status chip. Every chip has one width,
    worked out from every topic's status rather than from the rows on
    screen, which a list view measures alone (docs/specs/topic-status.md)."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self.now = now
        self.matching: set[str] | None = None
        self.chip_width = 0
        # The natural width of each status, as a chip draws it, and the dash's.
        self.chip_widths: list[int] = []
        self.chip_probe = Gtk.Label(css_classes=["status-chip", "caption"])
        # The list view makes only as many rows as it shows, and reuses them.
        self.slots: set[Adw.Clamp] = set()
        self.store = Gio.ListStore(item_type=TopicObject)
        self.filter = Gtk.CustomFilter.new(lambda item: self.matching is None or item.topic.id in self.matching)
        self.filtered = Gtk.FilterListModel(model=self.store, filter=self.filter)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup)
        factory.connect("bind", self._bind)
        self.view = QueueView(
            self._resize_chips, model=Gtk.NoSelection(model=self.filtered), factory=factory, single_click_activate=True
        )
        self.view.add_css_class("navigation-sidebar")

    def set_topics(self, topics: list[TopicView]) -> None:
        names = {format.NO_STATUS, *(topic.status.name for topic in topics if topic.status)}
        self.chip_widths = [self._natural_width(name) for name in names]
        self._resize_chips(self.view.allocated)
        self.store.splice(0, self.store.get_n_items(), [TopicObject(topic) for topic in topics])

    def _natural_width(self, name: str) -> int:
        self.chip_probe.set_label(name)
        return self.chip_probe.measure(Gtk.Orientation.HORIZONTAL, -1)[1]

    def _resize_chips(self, queue_width: int) -> bool:
        self.chip_width = format.chip_width(self.chip_widths, queue_width)
        for slot in self.slots:
            self._size(slot)
        return GLib.SOURCE_REMOVE

    def _size(self, slot: Adw.Clamp) -> None:
        """A slot of the chip's width."""
        slot.set_maximum_size(max(self.chip_width, 1))
        slot.set_tightening_threshold(max(self.chip_width, 1))
        slot.set_size_request(self.chip_width, -1)

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

    def _setup(self, factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        chip = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, single_line_mode=True, css_classes=["caption"])
        slot = Adw.Clamp(child=chip, valign=Gtk.Align.CENTER)
        self.slots.add(slot)
        self._size(slot)
        avatar = Adw.Avatar(size=36, show_initials=True, valign=Gtk.Align.CENTER)
        title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["dim-label", "caption"])
        date = Gtk.Label(valign=Gtk.Align.CENTER, css_classes=["dim-label", "caption", "numeric"])
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(title)
        text.append(subtitle)
        row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        for widget in (slot, avatar, text, date):
            row.append(widget)
        item.set_child(row)

    def _bind(self, factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        topic = item.get_item().topic
        slot, avatar, text, date = list(_children(item.get_child()))
        title, subtitle = list(_children(text))
        chip = slot.get_child()
        chip.set_label(format.chip_label(topic.status))
        chip.set_tooltip_text(topic.status.name if topic.status else None)
        chip.set_css_classes(["caption", *format.chip_classes(topic.status)])
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
