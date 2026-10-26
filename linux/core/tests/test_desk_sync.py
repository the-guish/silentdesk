"""The desk's sync rounds, run against fake connectors and an in-memory store."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from itertools import count

import pytest

from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.desk.adapters.clocks import FixedClock
from silentdesk.apps.desk.adapters.sqlcipher_topic_store import SqlcipherTopicStore
from silentdesk.apps.desk.application.desk import DeskService
from silentdesk.apps.desk.core.sync import round_order
from silentdesk.apps.desk.domain.topics import TopicRecord
from silentdesk.apps.desk.ports.topic_store import TopicStore
from silentdesk.contract import (
    Connector,
    Direction,
    Item,
    Project,
    RemoteError,
    ServiceStatus,
    SyncFailed,
    SyncResult,
    Topic,
    TopicStatus,
    UnknownItem,
    UnknownProject,
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
        # The topics as the service has them, for deleting.
        self.known: dict[str, Topic] = {}
        # Item keys whose deletion the service refuses.
        self.refused: set[str] = set()

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
        self.known.update({topic.key: topic for topic in result.topics})
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

    async def delete_item(self, topic_key: str, item_key: str) -> Topic | None:
        if item_key in self.refused:
            raise RemoteError(self._service, "Refused.")
        self.log.append(f"delete {topic_key}/{item_key}")
        topic = self.known[topic_key]
        items = [item for item in topic.items if item.key != item_key]
        if not items:
            del self.known[topic_key]
            return None
        # Titled from its first item, as Gmail titles a thread.
        self.known[topic_key] = replace(topic, title=f"From {items[0].key}", items=items)
        return self.known[topic_key]


class MemoryTopicStore(TopicStore):
    def __init__(self) -> None:
        self.records: list[TopicRecord] = []
        self.synced: str | None = None

    async def topics(self) -> list[TopicRecord]:
        return list(self.records)

    async def replace(self, service: str, records: Sequence[TopicRecord]) -> None:
        self.records = [r for r in self.records if r.service != service] + list(records)

    # Projects are tested through the CLI, on the real database.
    async def projects(self) -> list[Project]:
        return []

    async def save_project(self, project: Project) -> None:
        raise NotImplementedError

    async def delete_project(self, project_id: str) -> None:
        raise NotImplementedError

    async def move(self, topic_id: str, project_id: str | None) -> None:
        raise NotImplementedError

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
            replace(thread("t1", "Invoice", email("m1", "2026-10-01T09:00:00Z")), status=TopicStatus("Open", None)),
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
    assert by_key(store)["t1"].status is None, "the status is the connector's, not kept across syncs"


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


@pytest.mark.parametrize(
    "operation",
    [
        lambda desk: desk.history("T"),
        lambda desk: desk.reply("T", "hi"),
        lambda desk: desk.delete("T"),
        lambda desk: desk.delete_item("T", "i"),
        lambda desk: desk.move("T", None),
    ],
    ids=["history", "reply", "delete", "delete_item", "move"],
)
def test_a_topic_of_a_service_no_longer_wired_is_an_unknown_service(tmp_path, operation):
    store = SqlcipherTopicStore(SqlcipherDatabase(tmp_path / "silentdesk.db", FileKeyring(tmp_path / "keyring.json")))
    left = TopicRecord("T", "gone", "k", "t", [email("i", NOW, deletable=True)], NOW, NOW, deletable=True)
    asyncio.run(store.replace("gone", [left]))
    with pytest.raises(UnknownService, match="Unknown service 'gone'"):
        asyncio.run(operation(DeskService([], store, FixedClock(NOW))))


def test_a_project_deleted_while_a_move_waits_is_an_unknown_project(tmp_path):
    store = SqlcipherTopicStore(SqlcipherDatabase(tmp_path / "silentdesk.db", FileKeyring(tmp_path / "keyring.json")))
    asyncio.run(store.replace("s", [TopicRecord("T", "s", "k", "t", [email("i", NOW)], NOW, NOW, deletable=False)]))
    desk = DeskService([FakeConnector("s", [], [])], store, FixedClock(NOW))

    async def scenario() -> None:
        project = await desk.add_project("Work")
        # As a sync of the service would, hold its lock while the move waits.
        async with desk.locks["s"]:
            moving = asyncio.create_task(desk.move("T", project.id))
            await asyncio.sleep(0)
            await desk.delete_project(project.id)
        await moving

    with pytest.raises(UnknownProject):
        asyncio.run(scenario())


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


def test_a_topic_its_connector_can_delete_goes_at_once():
    service, store, log = synced(thread("t1", "A", email("1", NOW), email("2", NOW), deletable=True))

    asyncio.run(service.delete("id-1"))

    assert log == ["delete t1"]
    assert store.records == []


def test_a_topic_deletable_only_by_its_items_goes_item_by_item():
    service, store, log = synced(thread("t1", "A", email("1", NOW, deletable=True), email("2", NOW, deletable=True)))

    asyncio.run(service.delete("id-1"))

    assert log == ["delete t1/1", "delete t1/2"]
    assert store.records == []


def test_an_item_that_fails_stops_the_deletion_and_the_deleted_ones_stay_deleted():
    service, store, log = synced(thread("t1", "A", *(email(key, NOW, deletable=True) for key in ("1", "2", "3"))))
    service.connectors["gmail"].refused = {"2"}

    with pytest.raises(RemoteError):
        asyncio.run(service.delete("id-1"))

    assert log == ["delete t1/1"]
    assert [item.key for item in store.records[0].items] == ["2", "3"]


def test_a_topic_that_is_not_deletable_is_refused_before_its_connector():
    service, store, log = synced(thread("t1", "A", email("1", NOW, deletable=True), email("2", NOW)))

    with pytest.raises(Unsupported):
        asyncio.run(service.delete("id-1"))

    assert log == []
    assert len(store.records) == 1


def test_deleting_an_item_keeps_the_topic_as_its_connector_reports_it():
    service, store, log = synced(
        thread("t1", "A", email("1", NOW, deletable=True), email("2", "2026-10-01T09:00:00Z", deletable=True))
    )

    asyncio.run(service.delete_item("id-1", "1"))

    assert log == ["delete t1/1"]
    [record] = store.records
    assert (record.id, record.title) == ("id-1", "From 2")
    assert [item.key for item in record.items] == ["2"]
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
