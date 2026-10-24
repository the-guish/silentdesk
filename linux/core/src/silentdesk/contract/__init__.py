"""The interfaces applications expose to each other and to the outside.

Apps depend on each other only through these classes. They hold no logic:
abstract classes for behaviour, frozen dataclasses for the data they pass."""

from .desk import Desk, TopicView
from .mail import Mail
from .source import Direction, Item, ServiceStatus, Source, SyncResult

__all__ = ["Desk", "Direction", "Item", "Mail", "ServiceStatus", "Source", "SyncResult", "TopicView"]
