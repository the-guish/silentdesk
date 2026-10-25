"""The filter bar over the queue: Project and Service, then the filters the
user adds with the + button. Its state and rules are in `filters.py`. See
spec/filters.md."""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Gtk

from . import filters
from .filters import Choice, Field


class ChoiceFilter:
    """One filter: a button that names its values, and a list of them with
    check boxes, All first."""

    def __init__(self, field: Field, changed: Callable[[], None], remove: Callable[[Field], None] | None) -> None:
        self.field, self.changed = field, changed
        self.choices: list[Choice] = []
        self.chosen: frozenset[str] = frozenset()
        self.checks: dict[str | None, Gtk.CheckButton] = {}
        self._syncing = False

        self.search = Gtk.SearchEntry(placeholder_text=f"Find {field.title.lower()}")
        self.search.connect("search-changed", lambda _: self.list.invalidate_filter())
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["navigation-sidebar"])
        self.list.set_filter_func(self._row_shown)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.search)
        box.append(Gtk.ScrolledWindow(child=self.list, max_content_height=360, propagate_natural_height=True))
        if remove is not None:
            remove_button = Gtk.Button(label="Remove Filter", css_classes=["flat"])
            remove_button.connect("clicked", lambda _: remove(field))
            box.append(remove_button)
        self.popover = Gtk.Popover(child=box)
        self.popover.connect("show", lambda _: self.search.set_text(""))
        self.button = Gtk.MenuButton(popover=self.popover, always_show_arrow=True)
        self.set_choices([])

    def set_choices(self, choices: list[Choice]) -> bool:
        """Offers `choices`; drops chosen values no longer offered. Returns
        whether the chosen values changed."""
        before = self.chosen
        self.choices = choices
        self.chosen = filters.keep_offered(self.chosen, choices)
        while row := self.list.get_row_at_index(0):
            self.list.remove(row)
        self.checks = {}
        for value, text in [(None, "All"), *((choice.value, choice.label) for choice in choices)]:
            check = Gtk.CheckButton(label=text)
            check.connect("toggled", lambda _, value=value: self.click(value))
            self.checks[value] = check
            self.list.append(check)
        self._sync()
        return self.chosen != before

    def click(self, value: str | None) -> None:
        """What a click on a value's check box, or on All for None, does."""
        if self._syncing:
            return
        self.chosen = filters.toggle(self.chosen, value)
        self._sync()
        self.changed()

    def clear(self) -> None:
        self.chosen = frozenset()
        self._sync()

    @property
    def label(self) -> str:
        return self.button.get_label()

    def _sync(self) -> None:
        self._syncing = True
        for value, check in self.checks.items():
            check.set_active(value in self.chosen if value is not None else not self.chosen)
        self._syncing = False
        self.button.set_label(filters.label(self.field.title, self.chosen, self.choices))

    def _row_shown(self, row: Gtk.ListBoxRow) -> bool:
        return self.search.get_text().lower() in row.get_child().get_label().lower()


class FilterBar:
    """The bar: its filters at the left and the + button at the right."""

    def __init__(self, changed: Callable[[], None]) -> None:
        self.changed = changed
        # What each field offers, kept for filters added later.
        self.offered: dict[str, list[Choice]] = {
            filters.WAITING_ON.key: filters.WAITING_ON_CHOICES,
            filters.DELETABLE.key: filters.DELETABLE_CHOICES,
        }
        self.filters: dict[str, ChoiceFilter] = {}
        self.row = Gtk.Box(spacing=6)
        self.more_checks: dict[str, Gtk.CheckButton] = {}
        more_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for field in filters.MORE:
            check = Gtk.CheckButton(label=field.title)
            check.connect("toggled", lambda check, field=field: self._more_toggled(field, check.get_active()))
            self.more_checks[field.key] = check
            more_list.append(check)
        self.more = Gtk.MenuButton(
            icon_name="list-add-symbolic", tooltip_text="More Filters", popover=Gtk.Popover(child=more_list)
        )
        self.box = Gtk.Box(spacing=6, margin_start=6, margin_end=6, margin_top=6, margin_bottom=6)
        self.box.append(Gtk.ScrolledWindow(child=self.row, hexpand=True, vscrollbar_policy=Gtk.PolicyType.NEVER))
        self.box.append(self.more)
        for field in filters.FIELDS:
            if field.always:
                self.add(field)

    def add(self, field: Field) -> ChoiceFilter:
        """Adds a field's filter at the end of the row, on All."""
        if field.key not in self.filters:
            remove = None if field.always else self.remove
            choice_filter = ChoiceFilter(field, self.changed, remove)
            choice_filter.set_choices(self.offered.get(field.key, []))
            self.filters[field.key] = choice_filter
            self.row.append(choice_filter.button)
        if not field.always:
            self.more_checks[field.key].set_active(True)
        return self.filters[field.key]

    def remove(self, field: Field, notify: bool = True) -> None:
        """Removes an added filter, and its condition."""
        choice_filter = self.filters.pop(field.key, None)
        if choice_filter is None:
            return
        choice_filter.popover.popdown()
        self.row.remove(choice_filter.button)
        self.more_checks[field.key].set_active(False)
        if choice_filter.chosen and notify:
            self.changed()

    def set_choices(self, field: Field, choices: list[Choice]) -> bool:
        """Offers `choices` in a field's filter. Returns whether its chosen
        values changed."""
        self.offered[field.key] = choices
        choice_filter = self.filters.get(field.key)
        return choice_filter.set_choices(choices) if choice_filter else False

    def chosen(self) -> dict[str, frozenset[str]]:
        return {key: choice_filter.chosen for key, choice_filter in self.filters.items()}

    def clear(self) -> None:
        """Sets Project and Service to All and removes the added filters.
        The caller asks for the topics again."""
        for field in filters.MORE:
            self.remove(field, notify=False)
        for choice_filter in self.filters.values():
            choice_filter.clear()

    def _more_toggled(self, field: Field, active: bool) -> None:
        if active and field.key not in self.filters:
            self.add(field).button.popup()
        elif not active:
            self.remove(field)
