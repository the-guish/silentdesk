"""The Gmail app: the inbox as topics, one per thread."""

from __future__ import annotations

from ...contract import Connector, Database, Settings
from ...infra import browser
from ...infra.http import Http
from ...infra.keyring import Keyring
from .adapters.gmail_http import GmailHttpApi
from .adapters.keyring_credentials import KeyringCredentials
from .adapters.loopback_authorization import LoopbackAuthorization
from .adapters.sqlcipher_state_store import SqlcipherStateStore
from .application.gmail import Gmail

GMAIL_API = "https://gmail.googleapis.com"


def create(settings: Settings, database: Database, keyring: Keyring, http: Http) -> Connector:
    authorization = LoopbackAuthorization(
        settings.google_client_id, settings.google_client_secret, http, browser.open_url
    )
    api = GmailHttpApi(http, settings.base_url("gmail", GMAIL_API))
    return Gmail(api, authorization, KeyringCredentials(keyring), SqlcipherStateStore(database))
