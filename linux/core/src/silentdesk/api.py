"""The core's public API: one function per command in spec/cli.md.

The CLI and the GTK app use only this module. It is also where the apps are
wired together: each app's adapters, then the desk on top of every connector."""

from __future__ import annotations

from importlib.metadata import version as package_version
from typing import Literal, TypedDict

from .apps import desk as desk_app
from .apps import gmail, google
from .contract import Desk
from .infra.database import Database
from .infra.http import Http
from .infra.keyring import Keyring
from .infra.settings import Settings

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
    keyring = Keyring()
    database = Database(settings.data_dir / "silentdesk.db", keyring)
    http = Http()
    connectors = [
        gmail.create(settings, database, keyring, http),
        google.create(settings, database, keyring, http),
    ]
    return desk_app.create(connectors, settings, database)
