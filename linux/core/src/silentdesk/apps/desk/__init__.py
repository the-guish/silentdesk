"""The desk app: gathers the topics every connector finds into one queue, and
runs sync rounds. It reaches the connectors only through `silentdesk.contract`."""

from __future__ import annotations

from collections.abc import Sequence

from ...contract import Connector, Database, Desk, Settings
from .adapters.clocks import FixedClock, SystemClock
from .adapters.sqlcipher_topic_store import SqlcipherTopicStore
from .application.desk import DeskService


def create(connectors: Sequence[Connector], settings: Settings, database: Database) -> Desk:
    clock = FixedClock(settings.now) if settings.now else SystemClock()
    return DeskService(connectors, SqlcipherTopicStore(database), clock)
