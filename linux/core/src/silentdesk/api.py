"""The core's public API: one function per command in spec/cli.md.

The CLI and the GTK app use only this module. It is also where the apps are
wired together: each app's adapters, then the desk on top of every connector."""

from __future__ import annotations

from importlib.metadata import version as package_version
from typing import Literal, TypedDict

from .adapters.https_client import HttpsClient
from .adapters.secret_service_keyring import SecretServiceKeyring
from .adapters.sqlcipher_database import SqlcipherDatabase
from .adapters.system_browser import SystemBrowser
from .apps import desk as desk_app
from .apps import gmail, google_tasks
from .contract import Desk, Settings

CONTRACT = 1
"""The version of spec/cli.md this core implements."""


class Version(TypedDict):
    contract: int
    implementation: Literal["python"]
    version: str


def version() -> Version:
    return {"contract": CONTRACT, "implementation": "python", "version": package_version("silentdesk")}


def desk(settings: Settings) -> Desk:
    """The desk with every connector app wired in. Building it does no I/O."""
    keyring = SecretServiceKeyring()
    database = SqlcipherDatabase(settings.data_dir / "silentdesk.db", keyring)
    http = HttpsClient()
    browser = SystemBrowser()
    connectors = [
        gmail.create(settings, database, keyring, http, browser),
        google_tasks.create(settings, database, keyring, http, browser),
    ]
    return desk_app.create(connectors, settings, database)
