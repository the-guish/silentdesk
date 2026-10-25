"""The application: one desk and one core worker, for one window."""

from __future__ import annotations

import sys

from gi.repository import Adw
from silentdesk import api

from .window import MainWindow
from .worker import CoreWorker

APP_ID = "com.silentdesk.app"


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self.worker: CoreWorker | None = None
        self.connect("activate", self._activate)
        self.connect("shutdown", self._shutdown)

    def _activate(self, _: Adw.Application) -> None:
        window = self.get_active_window()
        if window is None:
            self.worker = CoreWorker()
            window = MainWindow(self, api.desk(), self.worker)
        window.present()

    def _shutdown(self, _: Adw.Application) -> None:
        if self.worker is not None:
            self.worker.stop()


def main() -> int:
    return Application().run(sys.argv)
