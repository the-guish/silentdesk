"""The interfaces applications expose to each other and to the outside.

Apps depend on each other only through these classes. They hold no logic:
abstract classes for behaviour, frozen dataclasses for the data they pass."""

from .connector import Connector, Direction, Item, ServiceStatus, SyncResult, Topic
from .desk import Desk, TopicView
from .mail import Mail

__all__ = ["Connector", "Desk", "Direction", "Item", "Mail", "ServiceStatus", "SyncResult", "Topic", "TopicView"]
