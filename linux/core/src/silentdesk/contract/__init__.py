"""The interfaces applications expose to each other and to the outside, and
the shared services they are given.

Apps depend on each other only through these classes. They hold no logic:
abstract classes for behaviour, frozen dataclasses for the data they pass."""

from .browser import Browser
from .connector import Connector, Direction, Item, Message, ServiceStatus, SyncResult, Topic
from .database import Database, StorageError
from .desk import Desk, TopicQuery, TopicView
from .errors import (
    AuthError,
    ConnectorError,
    NetworkError,
    RemoteError,
    SyncFailed,
    UnknownItem,
    UnknownService,
    UnknownTopic,
    Unsupported,
)
from .http import Http, Response
from .keyring import Keyring
from .oauth import OAuth, OAuthClient, Tokens
from .settings import Settings

__all__ = [
    "AuthError",
    "Browser",
    "Connector",
    "ConnectorError",
    "Database",
    "Desk",
    "Direction",
    "Http",
    "Item",
    "Keyring",
    "Message",
    "NetworkError",
    "OAuth",
    "OAuthClient",
    "RemoteError",
    "Response",
    "ServiceStatus",
    "Settings",
    "StorageError",
    "SyncFailed",
    "SyncResult",
    "Tokens",
    "Topic",
    "TopicQuery",
    "TopicView",
    "UnknownItem",
    "UnknownService",
    "UnknownTopic",
    "Unsupported",
]
