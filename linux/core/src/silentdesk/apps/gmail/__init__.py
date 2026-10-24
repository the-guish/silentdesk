"""The Gmail app: the inbox as topics, one per thread."""

from __future__ import annotations

from ...contract import Browser, Connector, Database, Http, Keyring, Settings
from .adapters.gmail_http import GmailHttpApi
from .adapters.keyring_credentials import KeyringCredentials
from .adapters.loopback_authorization import LoopbackAuthorization
from .adapters.sqlcipher_state_store import SqlcipherStateStore
from .application.gmail import Gmail

GMAIL_API = "https://gmail.googleapis.com"


def create(settings: Settings, database: Database, keyring: Keyring, http: Http, browser: Browser) -> Connector:
    authorization = LoopbackAuthorization(settings.google_client_id, settings.google_client_secret, http, browser)
    api = GmailHttpApi(http, settings.base_url("gmail", GMAIL_API))
    return Gmail(api, authorization, KeyringCredentials(keyring), SqlcipherStateStore(database))
