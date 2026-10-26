"""The interfaces applications expose to each other and to the outside, and
the shared services they are given.

Apps depend on each other only through these classes. They hold no logic:
abstract classes for behaviour, frozen dataclasses for the data they pass."""

from .browser import Browser
from .connector import (
    Connector,
    Direction,
    Item,
    Message,
    ServiceStatus,
    StatusCategory,
    SyncResult,
    Topic,
    TopicStatus,
)
from .database import Database, StorageError
from .desk import DEFAULT_PROJECT, Desk, Project, TopicQuery, TopicView
from .errors import (
    AuthError,
    ConnectorError,
    InvalidProjectName,
    InvalidQuery,
    NetworkError,
    RemoteError,
    SyncFailed,
    UnknownItem,
    UnknownProject,
    UnknownService,
    UnknownTopic,
    Unsupported,
)
from .http import Http, Response
from .keyring import Keyring
from .oauth import OAuth, OAuthClient, Tokens
from .settings import Settings

__all__ = [
    "DEFAULT_PROJECT",
    "AuthError",
    "Browser",
    "Connector",
    "ConnectorError",
    "Database",
    "Desk",
    "Direction",
    "Http",
    "InvalidProjectName",
    "InvalidQuery",
    "Item",
    "Keyring",
    "Message",
    "NetworkError",
    "OAuth",
    "OAuthClient",
    "Project",
    "RemoteError",
    "Response",
    "ServiceStatus",
    "Settings",
    "StatusCategory",
    "StorageError",
    "SyncFailed",
    "SyncResult",
    "Tokens",
    "Topic",
    "TopicQuery",
    "TopicStatus",
    "TopicView",
    "UnknownItem",
    "UnknownProject",
    "UnknownService",
    "UnknownTopic",
    "Unsupported",
]
