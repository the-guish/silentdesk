"""Wires the app's own adapters into its application."""

from __future__ import annotations

from ....contract import Connector, Database, Http, Keyring, OAuth, OAuthClient, Settings
from ..adapters.keyring_credentials import KeyringCredentials
from ..adapters.slack_authorization import SlackAuthorization
from ..adapters.slack_http import SlackHttpApi
from ..adapters.sqlcipher_state_store import SqlcipherStateStore
from ..application.slack import Slack

CALLBACK_PATH = "/slack/callback"


def slack_client(settings: Settings) -> OAuthClient | None:
    """The organization's Slack app, from the settings; None without a client ID."""
    if not settings.slack_client_id:
        return None
    return OAuthClient(
        service="slack",
        authorize_url=settings.base_url("slack", "https://slack.com") + "/oauth/v2/authorize",
        token_url=settings.base_url("slack", "https://slack.com") + "/api/oauth.v2.access",
        client_id=settings.slack_client_id,
        port=settings.slack_redirect_port,
        path=CALLBACK_PATH,
        scope_param="user_scope",
        scope_separator=",",
    )


def create(settings: Settings, database: Database, keyring: Keyring, http: Http, oauth: OAuth) -> Connector:
    base = settings.base_url("slack", "https://slack.com")
    authorization = SlackAuthorization(oauth, slack_client(settings), f"{base}/api/auth.revoke")
    return Slack(
        SlackHttpApi(http, f"{base}/api"), authorization, KeyringCredentials(keyring), SqlcipherStateStore(database)
    )
