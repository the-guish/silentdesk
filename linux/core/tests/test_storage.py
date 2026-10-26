"""The SQLCipher database and the stores built on it."""

from __future__ import annotations

import asyncio
import stat
from dataclasses import replace

import pytest

from silentdesk import api, cli
from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.local_settings import LocalSettings
from silentdesk.adapters.sqlcipher_database import MIGRATIONS, SqlcipherDatabase
from silentdesk.apps.desk.adapters.sqlcipher_topic_store import SqlcipherTopicStore
from silentdesk.apps.desk.domain.topics import TopicRecord
from silentdesk.apps.gmail.adapters.sqlcipher_state_store import SqlcipherStateStore as GmailStateStore
from silentdesk.apps.gmail.domain.state import GmailState
from silentdesk.apps.google_tasks.adapters.sqlcipher_state_store import SqlcipherStateStore as TasksStateStore
from silentdesk.apps.google_tasks.domain.state import GoogleState
from silentdesk.contract import Direction, Item, StatusCategory, StorageError, TopicStatus


@pytest.fixture
def keyring(tmp_path) -> FileKeyring:
    return FileKeyring(tmp_path / "keyring.json")


@pytest.fixture
def database(tmp_path, keyring) -> SqlcipherDatabase:
    return SqlcipherDatabase(tmp_path / "data" / "silentdesk.db", keyring)


def test_first_use_creates_a_private_encrypted_database_and_its_key(database, keyring):
    with database.transaction() as db:
        (version,) = db.execute("PRAGMA user_version").fetchone()

    assert version == len(list(MIGRATIONS.glob("*.sql")))
    assert len(keyring.get("database-key")) == 64
    assert stat.S_IMODE(database.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(database.path.parent.stat().st_mode) == 0o700
    # Encrypted: not even the SQLite header is readable.
    assert not database.path.read_bytes().startswith(b"SQLite format 3")


def test_the_database_reopens_with_its_key(database, keyring):
    with database.transaction() as db:
        db.execute("INSERT INTO desk_values (name, value) VALUES ('a', 'b')")

    reopened = SqlcipherDatabase(database.path, keyring)
    with reopened.transaction() as db:
        assert db.execute("SELECT value FROM desk_values").fetchall() == [("b",)]


def test_a_database_whose_key_is_missing_is_refused_not_replaced(database, keyring):
    with database.transaction():
        pass
    keyring.delete("database-key")

    with pytest.raises(StorageError, match="key is missing"), SqlcipherDatabase(database.path, keyring).transaction():
        pass
    assert keyring.get("database-key") is None


def test_a_wrong_key_is_a_storage_error(database, keyring):
    with database.transaction():
        pass
    keyring.set("database-key", "00" * 32)

    with pytest.raises(StorageError, match="cannot be opened"), SqlcipherDatabase(database.path, keyring).transaction():
        pass


def test_a_failed_transaction_is_rolled_back(database):
    with pytest.raises(RuntimeError), database.transaction() as db:
        db.execute("INSERT INTO desk_values (name, value) VALUES ('a', 'b')")
        raise RuntimeError
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM desk_values").fetchone() == (0,)


def record(id: str, service: str, key: str, *dates: str, deletable: bool = False) -> TopicRecord:
    items = [Item(f"{key}-{n}", Direction.INBOUND, "Ana", None, date, deletable) for n, date in enumerate(dates)]
    return TopicRecord(id, service, key, f"Topic {key}", items, "2026-10-01T00:00:00Z", max(dates), deletable)


def test_topic_store_keeps_topics_and_their_items_in_order(database):
    store = SqlcipherTopicStore(database)
    gmail = [record("1", "gmail", "t1", "2026-10-02T00:00:00Z", "2026-10-03T00:00:00Z")]
    tasks = [record("2", "tasks", "k1", "2026-10-04T00:00:00Z")]
    later = replace(
        record("3", "gmail", "t2", "2026-10-05T00:00:00Z", deletable=True),
        status=TopicStatus("In Progress", StatusCategory.IN_PROGRESS),
    )
    nameless = replace(record("4", "jira", "j1", "2026-10-06T00:00:00Z"), status=TopicStatus("Triage", None))

    asyncio.run(store.replace("gmail", gmail))
    asyncio.run(store.replace("tasks", tasks))
    asyncio.run(store.replace("gmail", [later]))
    asyncio.run(store.replace("jira", [nameless]))

    stored = {r.id: r for r in asyncio.run(store.topics())}
    assert sorted(stored) == ["2", "3", "4"]
    assert stored["2"] == tasks[0]
    assert stored["3"] == later
    assert stored["4"] == nameless
    with database.transaction() as db:
        # Topic 1's items went with it.
        assert db.execute("SELECT count(*) FROM desk_items").fetchone() == (3,)


def test_topic_store_keeps_when_topics_last_changed(database):
    store = SqlcipherTopicStore(database)
    assert asyncio.run(store.last_synced()) is None
    asyncio.run(store.set_last_synced("2026-10-24T12:00:00Z"))
    asyncio.run(store.set_last_synced("2026-10-24T12:02:00Z"))
    assert asyncio.run(store.last_synced()) == "2026-10-24T12:02:00Z"


def test_gmail_and_tasks_keep_their_own_state(database):
    gmail, tasks = GmailStateStore(database), TasksStateStore(database)
    asyncio.run(gmail.save(GmailState("ana@example.com", None)))
    asyncio.run(gmail.save(GmailState("ana@example.com", "123")))
    asyncio.run(tasks.save("tasks", GoogleState("ana@example.com")))

    assert asyncio.run(gmail.load()) == GmailState("ana@example.com", "123")
    assert asyncio.run(tasks.load("tasks")) == GoogleState("ana@example.com")

    asyncio.run(gmail.clear())
    asyncio.run(tasks.clear("tasks"))
    assert asyncio.run(gmail.load()) is None
    assert asyncio.run(tasks.load("tasks")) is None


def test_the_topics_command_prints_camel_case_json_newest_first(tmp_path, monkeypatch):
    settings = LocalSettings(tmp_path / "data", test_keyring=tmp_path / "keyring.json")
    database = SqlcipherDatabase(settings.data_dir / "silentdesk.db", FileKeyring(settings.test_keyring))
    store = SqlcipherTopicStore(database)
    review = TopicStatus("Code Review", StatusCategory.IN_PROGRESS)
    asyncio.run(store.replace("gmail", [replace(record("1", "gmail", "old", "2026-10-01T00:00:00Z"), status=review)]))
    asyncio.run(store.replace("tasks", [record("2", "tasks", "new", "2026-10-09T00:00:00Z")]))
    monkeypatch.setattr(api.LocalSettings, "from_environment", classmethod(lambda cls: settings))

    code, document = cli.run(["topics"], stdin=lambda: "")

    assert code == cli.EXIT_OK
    assert [topic["id"] for topic in document] == ["2", "1"]
    assert document[1]["status"] == {"name": "Code Review", "category": "inProgress"}
    assert document[0] == {
        "id": "2",
        "service": "tasks",
        "title": "Topic new",
        "items": [
            {
                "key": "new-0",
                "direction": "inbound",
                "author": "Ana",
                "url": None,
                "date": "2026-10-09T00:00:00Z",
                "deletable": False,
            }
        ],
        "projectId": None,
        "status": None,
        "updatedAt": "2026-10-09T00:00:00Z",
        "deletable": False,
    }


def test_upgrading_makes_gmail_topics_deletable_and_leaves_the_others(tmp_path, keyring):
    """Gmail syncs only the threads that change, so migration 0006 marks
    its existing topics as its next sync would."""
    before = tmp_path / "before"
    before.mkdir()
    for script in sorted(MIGRATIONS.glob("*.sql"))[:5]:
        (before / script.name).write_text(script.read_text())
    path = tmp_path / "silentdesk.db"
    with SqlcipherDatabase(path, keyring, before).transaction() as db:
        for id, service in [("1", "gmail"), ("2", "tasks")]:
            db.execute(
                "INSERT INTO desk_topics (id, service, key, title, created_at, updated_at) VALUES (?, ?, ?, 'T', 'd', 'd')",
                (id, service, f"k{id}"),
            )
            db.execute("INSERT INTO desk_items (topic_id, position, key, date) VALUES (?, 0, ?, 'd')", (id, f"i{id}"))

    upgraded = {r.service: r for r in asyncio.run(SqlcipherTopicStore(SqlcipherDatabase(path, keyring)).topics())}

    assert upgraded["gmail"].deletable and upgraded["gmail"].items[0].deletable
    assert not upgraded["tasks"].deletable and not upgraded["tasks"].items[0].deletable
