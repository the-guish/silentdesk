"""The filter bar over the queue: Project and Service, then the filters the
user adds with the + button. Its state and rules are in `filters.py`. See
docs/specs/filters.md."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from gi.repository import GLib, Gtk

from . import filters
from .filters import Choice, Field, Updated


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


# The Updated filter's forms, as filters.Updated names them, and units.
FORMS = ((None, "All"), ("within", "Within the last"), ("over", "More than"), ("between", "Between"))
UNITS = ("days", "weeks")


class DateFilter:
    """The Updated filter: All, Within the last, More than, or Between two
    days, as Jira's date filters offer."""

    def __init__(self, field: Field, changed: Callable[[], None], remove: Callable[[Field], None]) -> None:
        self.field, self.changed = field, changed
        self.updated: Updated | None = None
        self._syncing = False

        self.form = Gtk.DropDown.new_from_strings([text for _, text in FORMS])
        self.amount = Gtk.SpinButton.new_with_range(1, 999, 1)
        self.amount.set_value(7)
        self.unit = Gtk.DropDown.new_from_strings(UNITS)
        self.ago = Gtk.Label(label="ago")
        self.span = Gtk.Box(spacing=6)
        for widget in (self.amount, self.unit, self.ago):
            self.span.append(widget)
        today = date.today()
        self.first, self.last = Gtk.Calendar(), Gtk.Calendar()
        self.first.select_day(_glib_date(today - timedelta(days=7)))
        self.days = Gtk.Box(spacing=12)
        for title, calendar in (("From", self.first), ("To", self.last)):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            column.append(Gtk.Label(label=title, xalign=0, css_classes=["heading"]))
            column.append(calendar)
            self.days.append(column)
        for widget, signal in [
            (self.form, "notify::selected"),
            (self.amount, "value-changed"),
            (self.unit, "notify::selected"),
            (self.first, "day-selected"),
            (self.last, "day-selected"),
        ]:
            widget.connect(signal, lambda *_: self._read())
        remove_button = Gtk.Button(label="Remove Filter", css_classes=["flat"])
        remove_button.connect("clicked", lambda _: remove(field))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for widget in (self.form, self.span, self.days, remove_button):
            box.append(widget)
        self.popover = Gtk.Popover(child=box)
        self.button = Gtk.MenuButton(popover=self.popover, always_show_arrow=True)
        self._sync()

    def set_updated(self, updated: Updated | None) -> None:
        """Shows `updated` in the popover, then applies it as the user would."""
        self._syncing = True
        forms = [form for form, _ in FORMS]
        self.form.set_selected(forms.index(updated.form if updated else None))
        if updated:
            self.amount.set_value(updated.amount)
            self.unit.set_selected(UNITS.index(updated.unit))
            if updated.first:
                self.first.select_day(_glib_date(updated.first))
            if updated.last:
                self.last.select_day(_glib_date(updated.last))
        self._syncing = False
        self._read()

    @property
    def active(self) -> bool:
        return self.updated is not None

    @property
    def label(self) -> str:
        return self.button.get_label()

    def clear(self) -> None:
        self.updated = None
        self._sync()

    def _read(self) -> None:
        if self._syncing:
            return
        form = FORMS[self.form.get_selected()][0]
        if form is None:
            self.updated = None
        else:
            first, last = _date(self.first.get_date()), _date(self.last.get_date())
            self.updated = Updated(
                form,
                int(self.amount.get_value()),
                UNITS[self.unit.get_selected()],
                min(first, last),
                max(first, last),
            )
        self._sync()
        self.changed()

    def _sync(self) -> None:
        form = self.updated.form if self.updated else None
        self.span.set_visible(form in ("within", "over"))
        self.ago.set_visible(form == "over")
        self.days.set_visible(form == "between")
        self.button.set_label(filters.updated_label(self.updated))


def _date(moment: GLib.DateTime) -> date:
    return date(moment.get_year(), moment.get_month(), moment.get_day_of_month())


def _glib_date(day: date) -> GLib.DateTime:
    return GLib.DateTime.new_local(day.year, day.month, day.day, 0, 0, 0)


class FilterBar:
    """The bar: its filters at the left and the + button at the right."""

    def __init__(self, changed: Callable[[], None]) -> None:
        self.changed = changed
        # What each field offers, kept for filters added later.
        self.offered: dict[str, list[Choice]] = {
            filters.WAITING_ON.key: filters.WAITING_ON_CHOICES,
            filters.DELETABLE.key: filters.DELETABLE_CHOICES,
        }
        self.filters: dict[str, ChoiceFilter | DateFilter] = {}
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

    def add(self, field: Field) -> ChoiceFilter | DateFilter:
        """Adds a field's filter at the end of the row, on All."""
        if field.key not in self.filters:
            remove = None if field.always else self.remove
            if field == filters.UPDATED:
                new: ChoiceFilter | DateFilter = DateFilter(field, self.changed, self.remove)
            else:
                new = ChoiceFilter(field, self.changed, remove)
                new.set_choices(self.offered.get(field.key, []))
            self.filters[field.key] = new
            self.row.append(new.button)
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
        if notify and (choice_filter.active if isinstance(choice_filter, DateFilter) else choice_filter.chosen):
            self.changed()

    def set_choices(self, field: Field, choices: list[Choice]) -> bool:
        """Offers `choices` in a field's filter. Returns whether its chosen
        values changed."""
        self.offered[field.key] = choices
        choice_filter = self.filters.get(field.key)
        return choice_filter.set_choices(choices) if isinstance(choice_filter, ChoiceFilter) else False

    def chosen(self) -> dict[str, frozenset[str]]:
        return {key: f.chosen for key, f in self.filters.items() if isinstance(f, ChoiceFilter)}

    def updated(self) -> Updated | None:
        date_filter = self.filters.get(filters.UPDATED.key)
        return date_filter.updated if isinstance(date_filter, DateFilter) else None

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
