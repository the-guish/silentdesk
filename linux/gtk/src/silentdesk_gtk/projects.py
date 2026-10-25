"""Projects on screen: the topic screen's project button, which moves the
topic, and the Projects dialog, which renames and deletes them. See
spec/filters.md."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from gi.repository import Adw, Gtk
from silentdesk.contract import DEFAULT_PROJECT, Desk, Project, TopicView

from . import filters, format
from .worker import CoreWorker


class ProjectPicker:
    """A button that names the topic's project, and a list to move it to
    another, or to a new one named by what the user types."""

    def __init__(self, desk: Desk, worker: CoreWorker, toast: Callable[[str], None], moved: Callable[[], None]) -> None:
        """`moved` runs after the topic moves."""
        self.desk, self.worker, self.toast, self.moved = desk, worker, toast, moved
        self.topic: TopicView | None = None
        self.projects: list[Project] = []
        self.search = Gtk.SearchEntry(placeholder_text="Find or create a project")
        self.search.connect("search-changed", lambda _: self._show())
        self.search.connect("activate", lambda _: self._activate_first())
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["navigation-sidebar"])
        self.list.connect("row-activated", lambda _, row: row.choose())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.search)
        box.append(Gtk.ScrolledWindow(child=self.list, max_content_height=360, propagate_natural_height=True))
        self.popover = Gtk.Popover(child=box)
        self.popover.connect("show", lambda _: self._open())
        self.button = Gtk.MenuButton(popover=self.popover, always_show_arrow=True, tooltip_text="Move to a Project")

    def show_topic(self, topic: TopicView) -> None:
        self.topic = topic
        self._load()

    @property
    def label(self) -> str:
        return self.button.get_label()

    def move(self, project_id: str | None) -> None:
        """Moves the topic to a project, or to Default for None."""
        topic = self.topic
        self.popover.popdown()

        def done(_: object, error: BaseException | None) -> None:
            if error:
                self.toast(format.describe(error))
                return
            self.topic = replace(topic, project_id=project_id)
            self.toast(f"Moved to {filters.project_name(self.projects, project_id)}")
            self._update_label()
            self.moved()

        self.worker.run(self.desk.move(topic.id, project_id), done)

    def create(self, name: str) -> None:
        """Creates a project, then moves the topic to it."""

        def done(project: Project | None, error: BaseException | None) -> None:
            if error:
                self.toast(format.describe(error))
                return
            self.projects.append(project)
            self.move(project.id)

        self.worker.run(self.desk.add_project(name), done)

    def _load(self) -> None:
        def done(projects: list[Project] | None, error: BaseException | None) -> None:
            if error:
                self.toast(format.describe(error))
                return
            self.projects = projects
            self._update_label()
            self._show()

        self.worker.run(self.desk.projects(), done)

    def _open(self) -> None:
        self.search.set_text("")
        self._load()

    def _update_label(self) -> None:
        self.button.set_label(f"Project: {filters.project_name(self.projects, self.topic.project_id)}")

    def _show(self) -> None:
        self.list.remove_all()
        typed = self.search.get_text().strip().casefold()
        current = self.topic.project_id if self.topic else None
        rows: list[tuple[str, Callable[[], None], bool]] = [
            (choice.label, lambda value=value: self.move(value), value == current)
            for choice in filters.project_choices(self.projects)
            for value in [None if choice.value == DEFAULT_PROJECT else choice.value]
            if typed in choice.label.casefold()
        ]
        if name := filters.new_project_name(self.search.get_text(), self.projects):
            rows.append((f'New Project "{name}"', lambda name=name: self.create(name), False))
        for text, choose, chosen in rows:
            self.list.append(_Row(text, choose, chosen))

    def _activate_first(self) -> None:
        row = self.list.get_row_at_index(0)
        if row is not None:
            row.choose()


class _Row(Gtk.ListBoxRow):
    def __init__(self, text: str, choose: Callable[[], None], chosen: bool) -> None:
        super().__init__()
        self.choose = choose
        box = Gtk.Box(spacing=6)
        box.append(Gtk.Label(label=text, xalign=0, hexpand=True))
        box.append(Gtk.Image(icon_name="object-select-symbolic", opacity=1 if chosen else 0))
        self.set_child(box)
        self.text = text


class ProjectsDialog(Adw.PreferencesDialog):
    """Every project, to rename or delete, and a row to add one."""

    def __init__(self, desk: Desk, worker: CoreWorker, changed: Callable[[], None]) -> None:
        """`changed` runs after a project is added, renamed or deleted."""
        super().__init__(title="Projects", content_width=480, content_height=480)
        self.desk, self.worker, self.changed = desk, worker, changed
        self.projects: list[Project] = []
        self.last_error: str | None = None
        self.group = Adw.PreferencesGroup(
            description="Topics without a project are in Default. Deleting a project moves its topics there."
        )
        self.add_row = Adw.EntryRow(title="New project", show_apply_button=True)
        self.add_row.connect("apply", lambda row: self.add_project(row.get_text()))
        self.rows: list[Adw.EntryRow] = []
        self.group.add(self.add_row)
        page = Adw.PreferencesPage()
        page.add(self.group)
        self.add(page)
        self.load()

    def load(self) -> None:
        def done(projects: list[Project] | None, error: BaseException | None) -> None:
            if error:
                self._fail(error)
                return
            self.projects = projects
            self._show()

        self.worker.run(self.desk.projects(), done)

    def add_project(self, name: str) -> None:
        self._run(self.desk.add_project(name), lambda: self.add_row.set_text(""))

    def rename(self, project_id: str, name: str) -> None:
        self._run(self.desk.rename_project(project_id, name))

    def delete(self, project_id: str) -> None:
        self._run(self.desk.delete_project(project_id))

    def _run(self, call, then: Callable[[], None] = lambda: None) -> None:
        def done(_: object, error: BaseException | None) -> None:
            if error:
                self._fail(error)
            else:
                then()
                self.changed()
            self.load()

        self.worker.run(call, done)

    def _show(self) -> None:
        for row in self.rows:
            self.group.remove(row)
        self.rows = []
        for project in self.projects:
            row = Adw.EntryRow(title="Name", text=project.name, show_apply_button=True)
            row.connect("apply", lambda row, project=project: self.rename(project.id, row.get_text()))
            delete = Gtk.Button(
                icon_name="user-trash-symbolic", tooltip_text="Delete", valign=Gtk.Align.CENTER, css_classes=["flat"]
            )
            delete.connect("clicked", lambda _, project=project: self._confirm_delete(project))
            row.add_suffix(delete)
            self.group.add(row)
            self.rows.append(row)

    def _confirm_delete(self, project: Project) -> None:
        dialog = Adw.AlertDialog(
            heading=f"Delete {project.name}?", body="Its topics move to Default. The topics themselves stay."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _, response: response == "delete" and self.delete(project.id))
        dialog.present(self)

    def _fail(self, error: BaseException) -> None:
        self.last_error = format.describe(error)
        self.add_toast(Adw.Toast(title=self.last_error, timeout=6))
