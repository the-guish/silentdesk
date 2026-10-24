"""The interfaces applications expose to each other and to the outside, and
the shared services they are given.

Apps depend on each other only through these classes. They hold no logic:
abstract classes for behaviour, frozen dataclasses for the data they pass."""

from .browser import Browser
from .connector import Connector, Direction, Item, ServiceStatus, SyncResult, Topic, Unsupported
from .database import Database
from .desk import Desk, TopicView
from .http import Http, Response
from .keyring import Keyring
from .settings import Settings

__all__ = [
    "Browser",
    "Connector",
    "Database",
    "Desk",
    "Direction",
    "Http",
    "Item",
    "Keyring",
    "Response",
    "ServiceStatus",
    "Settings",
    "SyncResult",
    "Topic",
    "TopicView",
    "Unsupported",
]
