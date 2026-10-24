"""Wires the app's own adapters into its application."""

from __future__ import annotations

from ....contract import Connector, Database, Http, Keyring, Settings
from ..adapters.jira_http import JiraHttpApi
from ..adapters.keyring_credentials import KeyringCredentials
from ..adapters.sqlcipher_state_store import SqlcipherStateStore
from ..application.jira import Jira

# Atlassian's gateway, the only way in for scoped Jira Cloud API tokens.
GATEWAY = "https://api.atlassian.com/ex/jira"


def create(settings: Settings, database: Database, keyring: Keyring, http: Http) -> Connector:
    return Jira(
        JiraHttpApi(http),
        KeyringCredentials(keyring),
        SqlcipherStateStore(database),
        lambda site: settings.base_url("jira", site),
        lambda: settings.base_url("atlassian", GATEWAY),
    )
