import asyncio
import json
from urllib.parse import parse_qs, parse_qsl, unquote, urlsplit

import httpx
import pytest

from silentdesk.core import errors
from silentdesk.core.model import Direction, GmailMessage, GoogleTask, TasksAccount, Topic, VaultData
from silentdesk.core.ports import Config
from silentdesk.core.secret_names import GOOGLE_TASKS_REFRESH_TOKEN
from silentdesk.sources.base import ServiceStatus
from silentdesk.sources.tasks import TasksSource, api, domain
from silentdesk.sources.tasks.api import TaskMeta

from .fakes import make_host, mock_client
from .test_gmail import CONFIG, redirecting_browser

READONLY = "https://www.googleapis.com/auth/tasks.readonly"


# --- domain (tasks/mod.rs) ------------------------------------------------


def meta(id: str, title: str) -> TaskMeta:
    return TaskMeta(id, "L1", "My Tasks", title, None, None, "https://tasks.google.com/", "2026-10-24T09:00:00Z")


def test_each_task_gets_its_own_topic():
    data = VaultData()
    domain.apply_sync(data, [meta("1", "Draft plan"), meta("2", "")], "now")
    assert [t.title for t in data.topics] == ["Draft plan", "(untitled task)"]


def test_resync_follows_renames_and_drops_finished_tasks():
    data = VaultData()
    domain.apply_sync(data, [meta("1", "A"), meta("2", "B")], "now")
    topic_of_b = data.google_tasks[1].topic_id

    domain.apply_sync(data, [meta("2", "B, renamed"), meta("3", "C")], "later")
    assert data.google_tasks[0].topic_id == topic_of_b
    assert [t.title for t in data.topics] == ["B, renamed", "C"]

    domain.clear(data)
    assert data.topics == []


def test_sync_leaves_other_sources_alone():
    data = VaultData(
        topics=[Topic("g", "Mail", "now")],
        gmail_messages=[GmailMessage("m", "t", "g", Direction.INBOUND, "", "", "Mail", "d")],
    )
    domain.apply_sync(data, [meta("1", "A")], "now")
    domain.apply_sync(data, [], "later")
    assert [t.id for t in data.topics] == ["g"]


# --- api (tasks/api.rs) ---------------------------------------------------


def task(text: str) -> api.RawTask:
    return api.raw_task(json.loads(text))


def test_parses_an_open_task():
    m = api.to_meta(
        task("""{"id":"t1","title":" Draft Q4 plan ","status":"needsAction",
                 "due":"2026-10-30T00:00:00.000Z","updated":"2026-10-24T09:00:00.000Z",
                 "webViewLink":"https://tasks.google.com/task/t1",
                 "links":[{"type":"email","description":"Budget","link":"https://mail.google.com/x"}]}"""),
        "L1",
        "My Tasks",
    )
    assert m.title == "Draft Q4 plan"
    assert m.due == "2026-10-30"
    assert m.origin == "Gmail"
    assert m.list_title == "My Tasks"
    assert m.url == "https://tasks.google.com/task/t1"


def test_assignment_wins_over_links_and_missing_fields_are_fine():
    m = api.to_meta(
        task("""{"id":"t2","status":"needsAction","updated":"u",
                 "assignmentInfo":{"surfaceType":"DOCUMENT","linkToTask":"x"},
                 "links":[{"type":"email"}]}"""),
        "L1",
        "Work",
    )
    assert m.origin == "Docs"
    assert m.due is None
    assert m.title == ""
    assert m.url == "https://tasks.google.com/"


def test_unknown_surface_falls_back_to_links():
    m = api.to_meta(
        task('{"id":"t","assignmentInfo":{"surfaceType":"OTHER"},"links":[{"type":"x"},{"type":"chat_message"}]}'),
        "L",
        "l",
    )
    assert m.origin == "Chat"
    assert api.to_meta(task('{"id":"t","due":"2026-10"}'), "L", "l").due is None


def test_skips_completed_and_deleted():
    assert api.to_meta(task('{"id":"a","status":"completed"}'), "L", "l") is None
    assert api.to_meta(task('{"id":"b","status":"needsAction","deleted":true}'), "L", "l") is None


def test_list_ids_are_encoded_in_paths():
    assert api.endpoint(["lists", "a/b?c", "tasks"]) == "https://tasks.googleapis.com/tasks/v1/lists/a%2Fb%3Fc/tasks"
    assert api.endpoint(["users", "@me", "lists"]) == "https://tasks.googleapis.com/tasks/v1/users/@me/lists"


def test_pages_parse_without_items():
    page = api._page(api.raw_list)({"kind": "tasks#taskLists"})
    assert page.items == []
    assert page.next_page_token is None


# --- service (commands/tasks.rs) ------------------------------------------


class FakeGoogle:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_error: dict | None = None
        self.scope = f"{READONLY} openid https://www.googleapis.com/auth/userinfo.email"
        # list id -> (title, pages of tasks)
        self.lists: dict[str, tuple[str, list[list[dict]]]] = {}
        self.status: dict[str, tuple[int, object]] = {}

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.raw_path.decode().split("?")[0]
        if host == "oauth2.googleapis.com" and path == "/token":
            form = parse_qs(request.content.decode())
            if self.token_error is not None:
                return httpx.Response(400, json=self.token_error)
            if form["grant_type"] == ["authorization_code"]:
                return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt-new", "scope": self.scope})
            return httpx.Response(200, json={"access_token": "at"})
        if host == "oauth2.googleapis.com" and path == "/revoke":
            return httpx.Response(200)
        assert request.headers["authorization"] == "Bearer at"
        if path in self.status:
            status, body = self.status[path]
            return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
        if host == "openidconnect.googleapis.com" and path == "/v1/userinfo":
            return httpx.Response(200, json={"sub": "1", "email": "me@example.com"})
        assert host == "tasks.googleapis.com"
        page = int(request.url.params.get("pageToken", "0"))
        if path == "/tasks/v1/users/@me/lists":
            assert request.url.params["maxResults"] == "100"
            return httpx.Response(200, json={"items": [{"id": k, "title": v[0]} for k, v in self.lists.items()]})
        list_id = unquote(path.split("/")[4])
        pages = self.lists[list_id][1]
        body: dict = {"items": pages[page]}
        if page + 1 < len(pages):
            body["nextPageToken"] = str(page + 1)
        return httpx.Response(200, json=body)


def setup(data: VaultData | None = None, secrets=None, browser=None, config=CONFIG):
    google = FakeGoogle()
    host = make_host(data, secrets if secrets is not None else {GOOGLE_TASKS_REFRESH_TOKEN: "rt"}, config, browser)
    return google, host, TasksSource(host, mock_client(google.handler))


def connected(**data) -> VaultData:
    return VaultData(tasks_account=TasksAccount("me@example.com"), **data)


def raw(id: str, title: str, updated: str, **extra) -> dict:
    return {"id": id, "title": title, "status": "needsAction", "updated": updated, **extra}


def test_status_and_methods():
    async def run():
        _, _, source = setup(config=Config())
        assert await source.status() == ServiceStatus(False, False, None)
        _, _, source = setup(connected())
        assert await source.status() == ServiceStatus(True, True, "me@example.com")
        assert set(source.methods()) == {"tasks.status", "tasks.connect", "tasks.sync", "tasks.disconnect"}

    asyncio.run(run())


def test_not_configured_and_not_connected():
    async def run():
        _, _, source = setup(config=Config())
        with pytest.raises(errors.NotConfigured) as e:
            await source.sync()
        assert e.value.message == (
            "Google Tasks is not set up. Set SILENTDESK_GOOGLE_CLIENT_ID in .env (see docs/setup/google-tasks.md)."
        )
        _, _, source = setup()
        with pytest.raises(errors.NotConnected) as e:
            await source.sync()
        assert e.value.message == "Google Tasks is not connected."

    asyncio.run(run())


def test_connect_reads_the_email_and_stores_the_token():
    async def run():
        browser = redirecting_browser()
        stored = VaultData(tasks_account=TasksAccount("old@example.com"))
        google, host, source = setup(stored, browser=browser)
        status = await source.methods()["tasks.connect"]({})
        assert status == ServiceStatus(True, True, "me@example.com")
        assert host.secrets.get(GOOGLE_TASKS_REFRESH_TOKEN) == "rt-new"
        assert "/revoke" in google.paths()
        q = dict(parse_qsl(urlsplit(browser.opened[0]).query))
        assert q["scope"] == f"{READONLY} openid email"

    asyncio.run(run())


def test_connect_needs_tasks_readonly():
    async def run():
        google, host, source = setup(secrets={}, browser=redirecting_browser())
        google.scope = "openid email"
        with pytest.raises(errors.Auth) as e:
            await source.connect({})
        assert e.value.message == "Sign-in failed: Google Tasks access was not granted."
        assert host.secrets.get(GOOGLE_TASKS_REFRESH_TOKEN) is None

    asyncio.run(run())


def test_sync_pulls_every_open_task():
    async def run():
        google, host, source = setup(connected())
        google.lists = {
            "L1": ("My Tasks", [[raw("a", "Old", "2026-10-01T00:00:00Z")], [raw("b", "New", "2026-10-03T00:00:00Z")]]),
            "a/b": ("Work", [[raw("c", "Mid", "2026-10-02T00:00:00Z"), {"id": "d", "status": "completed"}]]),
        }
        views = await source.methods()["tasks.sync"]({})
        assert [v["title"] for v in views] == ["New", "Mid", "Old"]
        data = host.store.data()
        assert [t.task_id for t in data.google_tasks] == ["b", "c", "a"]
        assert data.google_tasks[1].list_title == "Work"
        tasks_call = next(r for r in google.requests if "a%2Fb" in r.url.raw_path.decode())
        assert tasks_call.url.raw_path.decode().startswith("/tasks/v1/lists/a%2Fb/tasks?")
        assert tasks_call.url.params.multi_items() == [
            ("maxResults", "100"),
            ("showCompleted", "false"),
            ("showHidden", "false"),
            ("showDeleted", "false"),
            ("showAssigned", "true"),
        ]

        # A finished task goes, with its topic; the others keep theirs.
        topic_of_b = data.google_tasks[0].topic_id
        google.lists = {"L1": ("My Tasks", [[raw("b", "New, renamed", "2026-10-04T00:00:00Z")]])}
        views = await source.sync()
        assert [(v["id"], v["title"]) for v in views] == [(topic_of_b, "New, renamed")]

    asyncio.run(run())


def test_paging_stops_after_max_pages():
    async def run():
        google, host, source = setup(connected())
        google.lists = {"L1": ("My Tasks", [[raw(str(i), f"T{i}", "u")] for i in range(25)])}
        await source.sync()
        assert len(host.store.data().google_tasks) == api.MAX_PAGES

    asyncio.run(run())


def test_api_errors():
    async def run():
        google, _, source = setup(connected())
        google.status["/tasks/v1/users/@me/lists"] = (403, {"error": {"message": "Tasks API has not been used"}})
        with pytest.raises(errors.Api) as e:
            await source.sync()
        assert e.value.message == "Google Tasks API error (403): Tasks API has not been used"

        google.status["/tasks/v1/users/@me/lists"] = (500, None)
        with pytest.raises(errors.Api) as e:
            await source.sync()
        assert e.value.message == "Google Tasks API error (500): Internal Server Error"

        google.status["/tasks/v1/users/@me/lists"] = (401, None)
        with pytest.raises(errors.Reauthorize):
            await source.sync()

    asyncio.run(run())


def test_dead_grant_deletes_the_token_and_keeps_topics():
    async def run():
        stored = connected(
            topics=[Topic("t1", "A", "now")],
            google_tasks=[GoogleTask("a", "L1", "My Tasks", "t1", None, None, "u", "d")],
        )
        google, host, source = setup(stored)
        google.token_error = {"error": "invalid_grant"}
        with pytest.raises(errors.Reauthorize) as e:
            await source.sync()
        assert e.value.message == "Google Tasks access was revoked or has expired. Connect again."
        assert host.secrets.get(GOOGLE_TASKS_REFRESH_TOKEN) is None
        assert [t.id for t in host.store.data().topics] == ["t1"]

    asyncio.run(run())


def test_disconnect_revokes_and_forgets_everything():
    async def run():
        stored = connected(
            topics=[Topic("t1", "A", "now")],
            google_tasks=[GoogleTask("a", "L1", "My Tasks", "t1", None, None, "u", "d")],
        )
        google, host, source = setup(stored)
        assert await source.methods()["tasks.disconnect"]({}) == ServiceStatus(True, False, None)
        assert "/revoke" in google.paths()
        assert host.secrets.get(GOOGLE_TASKS_REFRESH_TOKEN) is None
        data = host.store.data()
        assert data.topics == [] and data.google_tasks == [] and data.tasks_account is None

    asyncio.run(run())
