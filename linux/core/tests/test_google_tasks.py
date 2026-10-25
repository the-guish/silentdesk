"""The Google Tasks connector: its rules, its use cases and its HTTP adapter."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.https_client import HttpsClient
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.google_tasks.adapters.keyring_credentials import KeyringCredentials
from silentdesk.apps.google_tasks.adapters.sqlcipher_state_store import SqlcipherStateStore
from silentdesk.apps.google_tasks.adapters.tasks_http import TasksHttpApi
from silentdesk.apps.google_tasks.application.tasks import GoogleTasks
from silentdesk.apps.google_tasks.core import tasks
from silentdesk.apps.google_tasks.domain.tasks import GoogleTask, Grant, TaskList
from silentdesk.apps.google_tasks.ports.authorization import Authorization
from silentdesk.contract import AuthError, Unsupported

MY_TASKS = TaskList("list/1", "My Tasks")


def test_completed_and_deleted_tasks_are_not_open():
    task = GoogleTask(
        "t", "l", "L", " Call Bo ", False, False, None, None, "https://tasks.google.com/", "2026-10-24T08:00:00Z"
    )
    assert tasks.is_open(task)
    assert not tasks.is_open(GoogleTask(**{**task.__dict__, "completed": True}))
    assert not tasks.is_open(GoogleTask(**{**task.__dict__, "deleted": True}))
    assert tasks.topic(task).title == "Call Bo"
    assert tasks.topic(GoogleTask(**{**task.__dict__, "title": ""})).title == "Untitled task"


def test_the_adapter_pages_through_tasks_and_reads_where_they_came_from():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "pageToken" not in request.url.params:
            item = {
                "id": "t1",
                "title": "From mail",
                "updated": "u1",
                "links": [{"type": "email"}],
                "due": "2026-10-30T00:00:00.000Z",
            }
            return httpx.Response(200, json={"items": [item], "nextPageToken": "p2"})
        item = {
            "id": "t2",
            "status": "completed",
            "assignmentInfo": {"surfaceType": "DOCUMENT"},
            "webViewLink": "https://t/2",
        }
        return httpx.Response(200, json={"items": [item]})

    api = TasksHttpApi(
        HttpsClient(transport=httpx.MockTransport(handler)), "https://tasks.example/tasks/v1", "https://u"
    )
    first, second = asyncio.run(api.tasks("token", MY_TASKS))

    # The list ID is one path segment, even with a slash in it.
    assert seen[0].url.raw_path.startswith(b"/tasks/v1/lists/list%2F1/tasks?")
    assert seen[1].url.params["pageToken"] == "p2"
    assert (first.origin, first.due, first.url) == ("Gmail", "2026-10-30", "https://tasks.google.com/")
    assert (second.origin, second.completed, second.url) == ("Docs", True, "https://t/2")


class FakeAuthorization(Authorization):
    def __init__(self, refresh_error: AuthError | None = None):
        self.refresh_error, self.revoked = refresh_error, []

    @property
    def configured(self) -> bool:
        return True

    async def sign_in(self, scopes, required):
        return Grant("access", "refresh-2")

    async def access_token(self, refresh_token):
        if self.refresh_error:
            raise self.refresh_error
        return "access"

    async def revoke(self, refresh_token):
        self.revoked.append(refresh_token)


class FakeApi:
    async def email(self, token):
        return "ana@example.com"


def connector(tmp_path, authorization) -> tuple[GoogleTasks, FileKeyring]:
    keyring = FileKeyring(tmp_path / "keyring.json")
    database = SqlcipherDatabase(tmp_path / "silentdesk.db", keyring)
    return GoogleTasks(FakeApi(), authorization, KeyringCredentials(keyring), SqlcipherStateStore(database)), keyring


def test_reconnecting_with_another_grant_revokes_the_old_one(tmp_path):
    authorization = FakeAuthorization()
    app, keyring = connector(tmp_path, authorization)
    keyring.set("google-tasks-refresh-token", "refresh-1")

    status = asyncio.run(app.connect({}))

    assert (status.connected, status.account) == (True, "ana@example.com")
    assert authorization.revoked == ["refresh-1"]
    assert keyring.get("google-tasks-refresh-token") == "refresh-2"


def test_a_dead_grant_is_forgotten_on_sync(tmp_path):
    app, keyring = connector(tmp_path, FakeAuthorization(AuthError("tasks", "The sign-in has expired.")))
    keyring.set("google-tasks-refresh-token", "refresh-1")
    with pytest.raises(AuthError, match="Connect Google Tasks again"):
        asyncio.run(app.sync())
    assert keyring.get("google-tasks-refresh-token") is None


def test_google_tasks_is_read_only(tmp_path):
    app, _ = connector(tmp_path, FakeAuthorization())
    with pytest.raises(Unsupported):
        asyncio.run(app.delete_topic("t1"))
