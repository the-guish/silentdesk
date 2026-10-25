"""The Services dialog: every service, connected or not, with its connect
form or its Disconnect button."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from gi.repository import Adw, Gtk
from silentdesk.contract import Desk, ServiceStatus

from . import format, services
from .worker import CoreWorker


class ServicesDialog(Adw.PreferencesDialog):
    def __init__(self, desk: Desk, worker: CoreWorker, changed: Callable[[str, bool], None]) -> None:
        """`changed(service, connected)` runs after a service connects or
        disconnects."""
        super().__init__(title="Services", content_width=560, content_height=520)
        self.desk, self.worker, self.changed = desk, worker, changed
        self.statuses: list[ServiceStatus] = []
        self.busy: str | None = None
        self.last_error: str | None = None
        self.group = Adw.PreferencesGroup(
            description="SilentDesk reads each service with your own account, and keeps your sign-in in the keyring."
        )
        self.rows: list[Gtk.Widget] = []
        self.entries: dict[str, dict[str, Adw.EntryRow]] = {}
        page = Adw.PreferencesPage()
        page.add(self.group)
        self.add(page)
        self.load()

    def load(self) -> None:
        def done(statuses: list[ServiceStatus] | None, error: BaseException | None) -> None:
            if error:
                self._fail(format.describe(error))
                return
            self.statuses = statuses
            self._show()

        self.worker.run(self.desk.services(), done)

    def connect_service(self, service: str, values: Mapping[str, str]) -> None:
        """Connects with the form's values; browser sign-ins have none."""
        if self.busy:
            return
        if empty := services.missing(service, values):
            self._fail(f"Fill in: {', '.join(empty)}.")
            return
        self.busy = service
        self._show()

        def done(status: ServiceStatus | None, error: BaseException | None) -> None:
            self.busy = None
            if error:
                self._fail(format.describe(error))
                self._show()
                return
            self.add_toast(Adw.Toast(title=f"Connected {format.service_name(service)}"))
            self.changed(service, True)
            self.load()

        self.worker.run(self.desk.connect(service, services.connect_params(service, values)), done)

    def disconnect_service(self, service: str) -> None:
        if self.busy:
            return
        self.busy = service
        self._show()

        def done(_: object, error: BaseException | None) -> None:
            self.busy = None
            if error:
                self._fail(format.describe(error))
                self._show()
                return
            self.changed(service, False)
            self.load()

        self.worker.run(self.desk.disconnect(service), done)

    def _confirm_disconnect(self, service: str) -> None:
        dialog = Adw.AlertDialog(
            heading=f"Disconnect {format.service_name(service)}?", body=services.disconnect_warning(service)
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("disconnect", "Disconnect")
        dialog.set_response_appearance("disconnect", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _, response: response == "disconnect" and self.disconnect_service(service))
        dialog.present(self)

    def _fail(self, message: str) -> None:
        self.last_error = message
        self.add_toast(Adw.Toast(title=message, timeout=6))

    def _show(self) -> None:
        # What was typed survives the rebuild, such as after a failed connect.
        typed = {service: self._values(service) for service in self.entries}
        self.entries = {}
        for row in self.rows:
            self.group.remove(row)
        self.rows = [self._row(status, typed.get(status.service, {})) for status in self.statuses]
        for row in self.rows:
            self.group.add(row)

    def _row(self, status: ServiceStatus, typed: Mapping[str, str]) -> Gtk.Widget:
        name = format.service_name(status.service)
        if not status.configured:
            return Adw.ActionRow(title=name, subtitle=services.describe(status), sensitive=False)
        row = Adw.ExpanderRow(title=name, subtitle=services.describe(status))
        busy = self.busy == status.service
        if status.connected:
            button = Gtk.Button(label="Disconnecting…" if busy else "Disconnect", css_classes=["destructive-action"])
            button.connect("clicked", lambda _: self._confirm_disconnect(status.service))
        else:
            entries = self.entries[status.service] = {}
            for field in services.fields(status.service):
                entry = (Adw.PasswordEntryRow if field.secret else Adw.EntryRow)(title=field.title)
                entry.set_text(typed.get(field.name, ""))
                row.add_row(entry)
                entries[field.name] = entry
            label = "Connecting…" if busy else "Sign in with the browser" if not entries else "Connect"
            button = Gtk.Button(label=label, css_classes=["suggested-action"])
            button.connect("clicked", lambda _: self._submit(status.service))
        button.set_sensitive(self.busy is None)
        actions = Gtk.Box(halign=Gtk.Align.END, margin_top=8, margin_bottom=8, margin_end=8)
        actions.append(button)
        row.add_row(actions)
        row.set_expanded(busy)
        return row

    def _values(self, service: str) -> dict[str, str]:
        return {name: entry.get_text() for name, entry in self.entries.get(service, {}).items()}

    def _submit(self, service: str) -> None:
        self.connect_service(service, self._values(service))
