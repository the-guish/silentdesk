"""The Google app: Google Tasks, as topics with one item each."""

from __future__ import annotations

from ...contract import Connector, Database, Settings
from ...infra import browser
from ...infra.http import Http
from ...infra.keyring import Keyring
from .adapters.keyring_credentials import KeyringCredentials
from .adapters.loopback_authorization import LoopbackAuthorization
from .adapters.sqlcipher_state_store import SqlcipherStateStore
from .adapters.tasks_http import TasksHttpApi
from .application.tasks import GoogleTasks

TASKS_API = "https://tasks.googleapis.com"


def create(settings: Settings, database: Database, keyring: Keyring, http: Http) -> Connector:
    authorization = LoopbackAuthorization(
        settings.google_client_id, settings.google_client_secret, http, browser.open_url
    )
    api = TasksHttpApi(http, settings.base_url("tasks", TASKS_API))
    return GoogleTasks(api, authorization, KeyringCredentials(keyring), SqlcipherStateStore(database))
