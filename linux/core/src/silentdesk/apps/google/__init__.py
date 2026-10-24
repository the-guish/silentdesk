"""The Google app: Gmail and Google Tasks, which share one Google sign-in."""

from __future__ import annotations

from dataclasses import dataclass

from ...contract import Connector, Mail
from ...infra import browser
from ...infra.database import Database
from ...infra.http import Http
from ...infra.keyring import Keyring
from ...infra.settings import Settings
from .adapters.gmail_http import GmailHttpApi
from .adapters.keyring_credentials import KeyringCredentials
from .adapters.loopback_authorization import LoopbackAuthorization
from .adapters.sqlcipher_state_store import SqlcipherStateStore
from .adapters.tasks_http import TasksHttpApi
from .application.gmail import Gmail
from .application.tasks import GoogleTasks

GMAIL_API = "https://gmail.googleapis.com"
TASKS_API = "https://tasks.googleapis.com"


@dataclass(frozen=True)
class GoogleApp:
    gmail: Mail
    tasks: Connector


def create(settings: Settings, database: Database, keyring: Keyring, http: Http) -> GoogleApp:
    authorization = LoopbackAuthorization(
        settings.google_client_id, settings.google_client_secret, http, browser.open_url
    )
    credentials = KeyringCredentials(keyring)
    state = SqlcipherStateStore(database)
    gmail = Gmail(GmailHttpApi(http, settings.base_urls.get("gmail", GMAIL_API)), authorization, credentials, state)
    tasks = GoogleTasks(
        TasksHttpApi(http, settings.base_urls.get("tasks", TASKS_API)), authorization, credentials, state
    )
    return GoogleApp(gmail=gmail, tasks=tasks)
