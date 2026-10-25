"""The desk's sync rounds, run against fake connectors and an in-memory store."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from itertools import count

import pytest

from silentdesk.apps.desk.adapters.clocks import FixedClock
from silentdesk.apps.desk.application.desk import DeskService
from silentdesk.apps.desk.core.sync import round_order
from silentdesk.apps.desk.domain.topics import TopicRecord
from silentdesk.apps.desk.ports.topic_store import TopicStore
from silentdesk.contract import (
    Connector,
    Direction,
    Item,
    ServiceStatus,
    SyncFailed,
    SyncResult,
    Topic,
    UnknownItem,
    UnknownService,
    Unsupported,
)

NOW = "2026-10-24T12:00:00Z"


class FakeConnector(Connector):
    """Returns the queued results in turn, and logs every sync to `log`."""

    def __init__(self, service: str, results: list[SyncResult | Exception], log: list[str], connected=True):
        self._service = service
        self.results = results
        self.log = log
        self.connected = connected

    @property
    def service(self) -> str:
        return self._service

    async def status(self) -> ServiceStatus:
        return ServiceStatus(self._service, configured=True, connected=self.connected, account="me@example.com")

    async def sync(self) -> SyncResult:
        self.log.append(self._service)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        raise NotImplementedError

    async def disconnect(self) -> ServiceStatus:
        raise NotImplementedError

    async def reply(self, topic_key: str, body: str) -> None:
        raise NotImplementedError

    async def history(self, topic_key: str):
        raise NotImplementedError

    async def delete_topic(self, topic_key: str) -> None:
        self.log.append(f"delete {topic_key}")

    async def delete_item(self, topic_key: str, item_key: str) -> None:
        self.log.append(f"delete {topic_key}/{item_key}")


class MemoryTopicStore(TopicStore):
    def __init__(self) -> None:
        self.records: list[TopicRecord] = []
        self.synced: str | None = None

    async def topics(self) -> list[TopicRecord]:
        return list(self.records)

    async def replace(self, service: str, records: Sequence[TopicRecord]) -> None:
        self.records = [r for r in self.records if r.service != service] + list(records)

    async def last_synced(self) -> str | None:
        return self.synced

    async def set_last_synced(self, when: str) -> None:
        self.synced = when


def email(key: str, date: str, deletable: bool = False) -> Item:
    return Item(key=key, direction=Direction.INBOUND, author="Ana", url=None, date=date, deletable=deletable)


def thread(key: str, title: str, *items: Item, deletable: bool = False) -> Topic:
    return Topic(key=key, title=title, items=list(items), deletable=deletable)


def desk(*connectors: Connector) -> tuple[DeskService, MemoryTopicStore]:
    ids = count(1)
    store = MemoryTopicStore()
    return DeskService(connectors, store, FixedClock(NOW), new_id=lambda: f"id-{next(ids)}"), store


def by_key(store: MemoryTopicStore) -> dict[str, TopicRecord]:
    return {record.key: record for record in store.records}


def test_round_order_puts_gmail_last_and_unknown_services_after_known_ones():
    assert round_order(["gmail", "zulip", "tasks", "jira"]) == ["tasks", "jira", "gmail", "zulip"]


def test_a_round_syncs_connected_services_in_order():
    log: list[str] = []
    gmail = FakeConnector("gmail", [SyncResult([], [], complete=True)], log)
    tasks = FakeConnector("tasks", [SyncResult([], [], complete=True)], log)
    jira = FakeConnector("jira", [], log, connected=False)
    service, store = desk(gmail, tasks, jira)

    asyncio.run(service.sync())

    assert log == ["tasks", "gmail"]
    assert store.synced == NOW


def test_new_topics_get_an_id_and_their_newest_items_date():
    result = SyncResult(
        [thread("t1", "Invoice", email("m1", "2026-10-01T09:00:00Z"), email("m2", "2026-10-02T09:00:00Z"))],
        [],
        complete=False,
    )
    service, store = desk(FakeConnector("gmail", [result], []))

    asyncio.run(service.sync("gmail"))

    [record] = store.records
    assert (record.id, record.service, record.title) == ("id-1", "gmail", "Invoice")
    assert (record.created_at, record.updated_at) == (NOW, "2026-10-02T09:00:00Z")
    assert [item.key for item in record.items] == ["m1", "m2"]


def test_a_changed_topic_keeps_its_id_and_a_removed_one_goes():
    first = SyncResult(
        [
            thread("t1", "Invoice", email("m1", "2026-10-01T09:00:00Z")),
            thread("t2", "Lunch?", email("m2", "2026-10-01T10:00:00Z")),
        ],
        [],
        complete=True,
    )
    second = SyncResult(
        [thread("t1", "Re: Invoice", email("m1", "2026-10-01T09:00:00Z"), email("m3", "2026-10-03T09:00:00Z"))],
        ["t2"],
        complete=False,
    )
    service, store = desk(FakeConnector("gmail", [first, second], []))

    asyncio.run(service.sync("gmail"))
    asyncio.run(service.sync("gmail"))

    assert list(by_key(store)) == ["t1"]
    assert by_key(store)["t1"].id == "id-1"
    assert by_key(store)["t1"].title == "Re: Invoice"


def test_a_complete_result_drops_every_topic_it_does_not_list():
    first = SyncResult([thread("a", "A", email("1", NOW)), thread("b", "B", email("2", NOW))], [], complete=True)
    second = SyncResult([thread("b", "B", email("2", NOW))], [], complete=True)
    service, store = desk(FakeConnector("tasks", [first, second], []))

    asyncio.run(service.sync("tasks"))
    asyncio.run(service.sync("tasks"))

    assert list(by_key(store)) == ["b"]


def test_a_sync_leaves_other_services_topics_alone():
    gmail = FakeConnector("gmail", [SyncResult([thread("t1", "Mail", email("m1", NOW))], [], complete=True)], [])
    tasks = FakeConnector("tasks", [SyncResult([], [], complete=True)], [])
    service, store = desk(gmail, tasks)

    asyncio.run(service.sync("gmail"))
    asyncio.run(service.sync("tasks"))

    assert [(r.service, r.key) for r in store.records] == [("gmail", "t1")]


def test_a_failing_service_does_not_stop_the_round():
    log: list[str] = []
    tasks = FakeConnector("tasks", [RuntimeError("Google Tasks is down.")], log)
    gmail = FakeConnector("gmail", [SyncResult([thread("t1", "Mail", email("m1", NOW))], [], complete=True)], log)
    service, store = desk(gmail, tasks)

    with pytest.raises(SyncFailed) as raised:
        asyncio.run(service.sync())

    assert log == ["tasks", "gmail"]
    assert [(name, str(error)) for name, error in raised.value.failures] == [("tasks", "Google Tasks is down.")]
    assert list(by_key(store)) == ["t1"]


def test_syncing_an_unknown_service_is_an_error():
    service, _ = desk()
    with pytest.raises(UnknownService, match="Unknown service 'zulip'"):
        asyncio.run(service.sync("zulip"))


def synced(*found: Topic) -> tuple[DeskService, MemoryTopicStore, list[str]]:
    log: list[str] = []
    service, store = desk(FakeConnector("gmail", [SyncResult(list(found), [], complete=True)], log))
    asyncio.run(service.sync("gmail"))
    log.clear()
    return service, store, log


def test_a_topic_is_deletable_when_its_connector_says_so_or_all_its_items_are():
    service, _, _ = synced(
        thread("said", "A", email("1", NOW), deletable=True),
        thread("all", "B", email("2", NOW, deletable=True), email("3", NOW, deletable=True)),
        thread("some", "C", email("4", NOW, deletable=True), email("5", NOW)),
    )

    deletable = {view.title: view.deletable for view in asyncio.run(service.topics())}

    assert deletable == {"A": True, "B": True, "C": False}


def test_deleting_a_topic_goes_through_its_connector_and_drops_it():
    service, store, log = synced(thread("t1", "A", email("1", NOW, deletable=True)))

    asyncio.run(service.delete("id-1"))

    assert log == ["delete t1"]
    assert store.records == []


def test_a_topic_that_is_not_deletable_is_refused_before_its_connector():
    service, store, log = synced(thread("t1", "A", email("1", NOW, deletable=True), email("2", NOW)))

    with pytest.raises(Unsupported):
        asyncio.run(service.delete("id-1"))

    assert log == []
    assert len(store.records) == 1


def test_deleting_an_item_keeps_the_others_and_dates_the_topic_by_them():
    service, store, log = synced(
        thread("t1", "A", email("1", "2026-10-01T09:00:00Z", deletable=True), email("2", NOW, deletable=True))
    )

    asyncio.run(service.delete_item("id-1", "2"))

    assert log == ["delete t1/2"]
    [record] = store.records
    assert [item.key for item in record.items] == ["1"]
    assert record.updated_at == "2026-10-01T09:00:00Z"


def test_deleting_the_last_item_drops_the_topic():
    service, store, _ = synced(thread("t1", "A", email("1", NOW, deletable=True)))

    asyncio.run(service.delete_item("id-1", "1"))

    assert store.records == []


def test_an_item_that_is_not_deletable_or_not_there_is_refused():
    service, _, log = synced(thread("t1", "A", email("1", NOW), deletable=True))

    with pytest.raises(Unsupported):
        asyncio.run(service.delete_item("id-1", "1"))
    with pytest.raises(UnknownItem):
        asyncio.run(service.delete_item("id-1", "nope"))

    assert log == []
