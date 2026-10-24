"""Wires the app's own adapters into its application."""

from __future__ import annotations

from ....contract import Browser, Connector, Database, Http, Keyring, Settings
from ..adapters.keyring_credentials import KeyringCredentials
from ..adapters.loopback_authorization import LoopbackAuthorization
from ..adapters.sqlcipher_state_store import SqlcipherStateStore
from ..adapters.tasks_http import TasksHttpApi
from ..application.tasks import GoogleTasks

TASKS_API = "https://tasks.googleapis.com"


def create(settings: Settings, database: Database, keyring: Keyring, http: Http, browser: Browser) -> Connector:
    authorization = LoopbackAuthorization(settings.google_client_id, settings.google_client_secret, http, browser)
    api = TasksHttpApi(http, settings.base_url("tasks", TASKS_API))
    return GoogleTasks(api, authorization, KeyringCredentials(keyring), SqlcipherStateStore(database))
