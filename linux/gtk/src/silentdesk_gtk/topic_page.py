"""The topic screen: a topic's items, or its conversation when the service
has one, with Reply and Delete where its connector offers them."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from gi.repository import Adw, Gtk, Pango
from silentdesk.contract import Desk, Direction, Message, TopicView, Unsupported

from . import format, services
from .worker import CoreWorker


class TopicPage(Adw.NavigationPage):
    def __init__(
        self,
        topic: TopicView,
        desk: Desk,
        worker: CoreWorker,
        now: Callable[[], datetime],
        toast: Callable[[str], None],
        replied: Callable[[TopicView], None],
        deleted: Callable[[TopicView], None],
    ) -> None:
        super().__init__(title=topic.title)
        self.topic, self.desk, self.worker, self.now = topic, desk, worker, now
        self.toast, self.replied, self.deleted = toast, replied, deleted
        self.loading = True
        self.sending = False
        # What the list shows, as (heading, text) pairs: the items, until the
        # conversation comes.
        self.entries: list[tuple[str, str]] = []
        self.showing = "items"

        header = Adw.HeaderBar(
            title_widget=Adw.WindowTitle(title=topic.title, subtitle=format.service_name(topic.service))
        )
        self.spinner = Gtk.Spinner(spinning=True)
        header.pack_end(self.spinner)
        self.delete_button: Gtk.Button | None = None
        if topic.service in services.DELETIONS:
            self.delete_button = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete")
            self.delete_button.connect("clicked", lambda _: self._confirm_delete())
            header.pack_end(self.delete_button)

        self.list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START, css_classes=["boxed-list"]
        )
        clamp = Adw.Clamp(child=self.list, maximum_size=760, margin_top=12, margin_bottom=12)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        view = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=clamp, vexpand=True))
        view.add_top_bar(header)

        self.reply_view: Gtk.TextView | None = None
        self.send_button: Gtk.Button | None = None
        if topic.service in services.CAN_REPLY:
            view.add_bottom_bar(self._reply_bar())

        self.set_child(view)
        self._show_items()
        self._update()
        self._load_history()

    def send(self) -> None:
        """Sends the reply box's text as a reply in the topic."""
        buffer = self.reply_view.get_buffer()
        body = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        if self.sending or not body.strip():
            return
        self.sending = True
        self._update()

        def done(_: object, error: BaseException | None) -> None:
            self.sending = False
            self._update()
            if error:
                self.toast(format.describe(error))
                return
            buffer.set_text("")
            self.toast("Reply sent")
            self.replied(self.topic)

        self.worker.run(self.desk.reply(self.topic.id, body), done)

    def delete(self) -> None:
        """Deletes the topic in its service, without asking."""
        if self.sending:
            return
        self.sending = True
        self._update()

        def done(_: object, error: BaseException | None) -> None:
            self.sending = False
            self._update()
            if error:
                self.toast(format.describe(error))
                return
            self.deleted(self.topic)

        self.worker.run(self.desk.delete(self.topic.id), done)

    def _confirm_delete(self) -> None:
        deletion = services.DELETIONS[self.topic.service]
        dialog = Adw.AlertDialog(heading=deletion.heading, body=deletion.body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _, response: response == "delete" and self.delete())
        dialog.present(self)

    def _load_history(self) -> None:
        def done(messages: list[Message] | None, error: BaseException | None) -> None:
            self.loading = False
            self._update()
            if isinstance(error, Unsupported):
                return
            if error:
                self.toast(format.describe(error))
                return
            self._show_messages(messages)

        self.worker.run(self.desk.history(self.topic.id), done)

    def _show_items(self) -> None:
        for item in self.topic.items:
            heading = self._heading(item.author, item.direction, item.date)
            self._add(heading, "", item.url)
        self.showing = "items"

    def _show_messages(self, messages: list[Message]) -> None:
        self.list.remove_all()
        self.entries = []
        for message in messages:
            self._add(self._heading(message.author, message.direction, message.date), message.text, None)
        self.showing = "history"

    def _heading(self, author: str | None, direction: Direction | None, date: str) -> str:
        who = author or format.service_name(self.topic.service)
        if direction == Direction.OUTBOUND:
            who = f"{who} (you)"
        return f"{who} · {format.short_date(date, self.now())}"

    def _add(self, heading: str, text: str, url: str | None) -> None:
        self.entries.append((heading, text))
        row = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        column.append(Gtk.Label(label=heading, xalign=0, css_classes=["heading"]))
        if text:
            column.append(
                Gtk.Label(label=text, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True)
            )
        row.append(column)
        if url:
            button = Gtk.Button(
                icon_name="adw-external-link-symbolic",
                tooltip_text=f"Open in {format.service_name(self.topic.service)}",
                valign=Gtk.Align.CENTER,
                css_classes=["flat"],
            )
            button.connect("clicked", lambda _: Gtk.UriLauncher(uri=url).launch(self.get_root(), None, None))
            row.append(button)
        self.list.append(row)

    def _reply_bar(self) -> Gtk.Widget:
        self.reply_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8)
        self.reply_view.set_left_margin(8)
        self.reply_view.set_right_margin(8)
        self.reply_view.get_buffer().connect("changed", lambda _: self._update())
        scroller = Gtk.ScrolledWindow(
            child=self.reply_view, hexpand=True, min_content_height=72, max_content_height=200, css_classes=["card"]
        )
        scroller.set_propagate_natural_height(True)
        self.send_button = Gtk.Button(label="Send", valign=Gtk.Align.END, css_classes=["suggested-action"])
        self.send_button.connect("clicked", lambda _: self.send())
        bar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        bar.append(scroller)
        bar.append(self.send_button)
        return bar

    def _update(self) -> None:
        self.spinner.set_spinning(self.loading or self.sending)
        self.spinner.set_visible(self.loading or self.sending)
        if self.delete_button:
            self.delete_button.set_sensitive(not self.sending)
        if self.send_button:
            buffer = self.reply_view.get_buffer()
            has_text = bool(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip())
            self.send_button.set_sensitive(has_text and not self.sending)
            self.reply_view.set_editable(not self.sending)
