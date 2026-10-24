"""The desk app: turns what every source finds into one queue of topics, and
runs sync rounds. It reaches the sources only through `silentdesk.contract`."""

from __future__ import annotations

from collections.abc import Sequence

from ...contract import Desk, Source
from ...infra.database import Database
from ...infra.settings import Settings
from .adapters.clocks import FixedClock, SystemClock
from .adapters.sqlcipher_topic_store import SqlcipherTopicStore
from .application.desk import DeskService


def create(sources: Sequence[Source], settings: Settings, database: Database) -> Desk:
    clock = FixedClock(settings.now) if settings.now else SystemClock()
    return DeskService(sources, SqlcipherTopicStore(database), clock)
