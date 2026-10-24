"""The SQLCipher database and the stores built on it."""

from __future__ import annotations

import asyncio
import stat

import pytest

from silentdesk import api, cli
from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.local_settings import LocalSettings
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.desk.adapters.sqlcipher_topic_store import SqlcipherTopicStore
from silentdesk.apps.desk.domain.topics import TopicRecord
from silentdesk.apps.gmail.adapters.sqlcipher_state_store import SqlcipherStateStore as GmailStateStore
from silentdesk.apps.gmail.domain.state import GmailState
from silentdesk.apps.google_tasks.adapters.sqlcipher_state_store import SqlcipherStateStore as TasksStateStore
from silentdesk.apps.google_tasks.domain.state import GoogleState
from silentdesk.contract import Direction, Item, StorageError


@pytest.fixture
def keyring(tmp_path) -> FileKeyring:
    return FileKeyring(tmp_path / "keyring.json")


@pytest.fixture
def database(tmp_path, keyring) -> SqlcipherDatabase:
    return SqlcipherDatabase(tmp_path / "data" / "silentdesk.db", keyring)


def test_first_use_creates_a_private_encrypted_database_and_its_key(database, keyring):
    with database.transaction() as db:
        (version,) = db.execute("PRAGMA user_version").fetchone()

    assert version == 1
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


def record(id: str, service: str, key: str, *dates: str) -> TopicRecord:
    items = [Item(f"{key}-{n}", Direction.INBOUND, "Ana", None, date) for n, date in enumerate(dates)]
    return TopicRecord(id, service, key, f"Topic {key}", items, "2026-10-01T00:00:00Z", max(dates))


def test_topic_store_keeps_topics_and_their_items_in_order(database):
    store = SqlcipherTopicStore(database)
    gmail = [record("1", "gmail", "t1", "2026-10-02T00:00:00Z", "2026-10-03T00:00:00Z")]
    tasks = [record("2", "tasks", "k1", "2026-10-04T00:00:00Z")]

    asyncio.run(store.replace("gmail", gmail))
    asyncio.run(store.replace("tasks", tasks))
    asyncio.run(store.replace("gmail", [record("3", "gmail", "t2", "2026-10-05T00:00:00Z")]))

    stored = {r.id: r for r in asyncio.run(store.topics())}
    assert sorted(stored) == ["2", "3"]
    assert stored["2"] == tasks[0]
    with database.transaction() as db:
        # Topic 1's items went with it.
        assert db.execute("SELECT count(*) FROM desk_items").fetchone() == (2,)


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
    asyncio.run(store.replace("gmail", [record("1", "gmail", "old", "2026-10-01T00:00:00Z")]))
    asyncio.run(store.replace("tasks", [record("2", "tasks", "new", "2026-10-09T00:00:00Z")]))
    monkeypatch.setattr(api.LocalSettings, "from_environment", classmethod(lambda cls: settings))

    code, document = cli.run(["topics"])

    assert code == cli.EXIT_OK
    assert [topic["id"] for topic in document] == ["2", "1"]
    assert document[0] == {
        "id": "2",
        "service": "tasks",
        "title": "Topic new",
        "items": [
            {"key": "new-0", "direction": "inbound", "author": "Ana", "url": None, "date": "2026-10-09T00:00:00Z"}
        ],
        "updatedAt": "2026-10-09T00:00:00Z",
    }
