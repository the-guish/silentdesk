"""Wires the app's own adapters into its application."""

from __future__ import annotations

from ....contract import Connector, Database, Http, Keyring, OAuth, OAuthClient, Settings
from ..adapters.google_authorization import GoogleAuthorization
from ..adapters.keyring_credentials import KeyringCredentials
from ..adapters.sqlcipher_state_store import SqlcipherStateStore
from ..adapters.tasks_http import TasksHttpApi
from ..application.tasks import GoogleTasks


def google_client(settings: Settings) -> OAuthClient | None:
    """Google's OAuth client, from the settings; None without a client ID."""
    if not settings.google_client_id:
        return None
    return OAuthClient(
        service="tasks",
        authorize_url=settings.base_url("google-accounts", "https://accounts.google.com") + "/o/oauth2/v2/auth",
        token_url=settings.base_url("google-oauth", "https://oauth2.googleapis.com") + "/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        # A refresh token, asked for again on every sign-in.
        extra={"access_type": "offline", "prompt": "consent"},
    )


def create(settings: Settings, database: Database, keyring: Keyring, http: Http, oauth: OAuth) -> Connector:
    revoke_url = settings.base_url("google-oauth", "https://oauth2.googleapis.com") + "/revoke"
    api = TasksHttpApi(
        http,
        settings.base_url("tasks", "https://tasks.googleapis.com") + "/tasks/v1",
        settings.base_url("google-userinfo", "https://openidconnect.googleapis.com") + "/v1/userinfo",
    )
    authorization = GoogleAuthorization(oauth, google_client(settings), revoke_url)
    return GoogleTasks(api, authorization, KeyringCredentials(keyring), SqlcipherStateStore(database))
