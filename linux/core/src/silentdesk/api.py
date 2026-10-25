"""The core's public API: one function per command in spec/cli.md.

The CLI and the GTK app use only this module. It is also where the apps are
wired together: each app's adapters, then the desk on top of every connector."""

from __future__ import annotations

from importlib.metadata import version as package_version
from typing import Literal, TypedDict

from .adapters.file_keyring import FileKeyring
from .adapters.https_client import HttpsClient
from .adapters.local_settings import LocalSettings
from .adapters.secret_service_keyring import SecretServiceKeyring
from .adapters.sqlcipher_database import SqlcipherDatabase
from .adapters.system_browser import SystemBrowser
from .apps.desk import wiring as desk_wiring
from .apps.github import wiring as github_wiring
from .apps.gmail import wiring as gmail_wiring
from .apps.google_tasks import wiring as google_tasks_wiring
from .contract import Desk

CONTRACT = 1
"""The version of spec/cli.md this core implements."""


class Version(TypedDict):
    contract: int
    implementation: Literal["python"]
    version: str


def version() -> Version:
    return {"contract": CONTRACT, "implementation": "python", "version": package_version("silentdesk")}


def desk(settings: LocalSettings | None = None) -> Desk:
    """The desk with every connector app wired in, with settings from the
    environment unless given. Building it does no I/O."""
    settings = settings or LocalSettings.from_environment()
    keyring = FileKeyring(settings.test_keyring) if settings.test_keyring else SecretServiceKeyring()
    database = SqlcipherDatabase(settings.data_dir / "silentdesk.db", keyring)
    http = HttpsClient(allow_loopback_http=settings.test_base_url is not None)
    browser = SystemBrowser()
    connectors = [
        gmail_wiring.create(settings, database, keyring, http, browser),
        github_wiring.create(settings, database, keyring, http),
        google_tasks_wiring.create(settings, database, keyring, http, browser),
    ]
    return desk_wiring.create(connectors, settings, database)
