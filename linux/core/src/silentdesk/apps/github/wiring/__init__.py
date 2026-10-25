"""Wires the app's own adapters into its application."""

from __future__ import annotations

from ....contract import Connector, Database, Http, Keyring, Settings
from ..adapters.github_http import GitHubHttpApi
from ..adapters.keyring_credentials import KeyringCredentials
from ..adapters.sqlcipher_state_store import SqlcipherStateStore
from ..application.github import GitHub


def create(settings: Settings, database: Database, keyring: Keyring, http: Http) -> Connector:
    return GitHub(
        GitHubHttpApi(http),
        KeyringCredentials(keyring),
        SqlcipherStateStore(database),
        lambda endpoint: settings.base_url("github", endpoint.api_base),
    )
