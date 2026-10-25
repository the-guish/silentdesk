"""The Gmail connector: replies, threads, its HTTP adapter and its syncs."""

from __future__ import annotations

import asyncio
import base64
import gc
import json

import httpx
import pytest

from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.https_client import HttpsClient
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.gmail.adapters.gmail_http import GmailHttpApi
from silentdesk.apps.gmail.adapters.keyring_credentials import KeyringCredentials
from silentdesk.apps.gmail.adapters.sqlcipher_state_store import SqlcipherStateStore
from silentdesk.apps.gmail.application.gmail import Gmail
from silentdesk.apps.gmail.core import gmail
from silentdesk.apps.gmail.domain.gmail import GmailMessage, Grant, Original
from silentdesk.apps.gmail.domain.state import GmailState
from silentdesk.apps.gmail.ports.authorization import Authorization
from silentdesk.apps.gmail.ports.gmail_api import GmailApi, Profile
from silentdesk.contract import AuthError, Direction, RemoteError, UnknownTopic

RECEIVED = Original(Direction.INBOUND, "Ana <ana@x.com>", "me@x.com", "", "Invoice", "<m1@x.com>", "<m0@x.com>")


def test_a_reply_goes_to_the_sender_in_the_same_thread():
    raw = gmail.reply(RECEIVED, "Thanks\nAna")
    head, body = raw.split("\r\n\r\n")
    assert head.split("\r\n") == [
        "To: Ana <ana@x.com>",
        "Subject: Re: Invoice",
        "In-Reply-To: <m1@x.com>",
        "References: <m0@x.com> <m1@x.com>",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "Content-Transfer-Encoding: base64",
    ]
    assert base64.b64decode(body) == b"Thanks\r\nAna"


def test_reply_headers_cannot_be_injected_and_non_ascii_subjects_are_encoded():
    sent = Original(Direction.OUTBOUND, "me@x.com", "bo@x.com\r\nBcc: eve@x.com", "", "Re: Café", "", "")
    head = gmail.reply(sent, "Hi").split("\r\n\r\n")[0].split("\r\n")
    assert head[0] == "To: bo@x.com Bcc: eve@x.com"
    assert head[1] == "Subject: =?UTF-8?B?" + base64.b64encode("Re: Café".encode()).decode() + "?="
    assert not any(line.startswith("In-Reply-To") for line in head)


def message(id: str, thread: str, date: str, subject: str = "Invoice", sender: str = "Ana Ruiz <ana@x.com>"):
    return GmailMessage(id, thread, Direction.INBOUND, sender, subject, date)


def test_a_thread_is_one_topic_titled_by_its_first_message():
    topic = gmail.topic(
        "t1", [message("b", "t1", "2026-10-02T00:00:00Z", "Re: Invoice"), message("a", "t1", "2026-10-01T00:00:00Z")]
    )
    assert (topic.key, topic.title) == ("t1", "Invoice")
    assert [(i.key, i.author) for i in topic.items] == [("a", "Ana Ruiz"), ("b", "Ana Ruiz")]
    assert gmail.topic("t2", [message("c", "t2", "d", subject=" ")]).title == "(no subject)"


def http_api(handler) -> GmailHttpApi:
    async def no_wait(seconds: float) -> None:
        pass

    return GmailHttpApi(HttpsClient(transport=httpx.MockTransport(handler)), "https://gmail.example", sleep=no_wait)


def test_the_adapter_retries_rate_limits_and_skips_drafts_and_vanished_messages():
    attempts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        message_id = request.url.path.rsplit("/", 1)[-1]
        attempts[message_id] = attempts.get(message_id, 0) + 1
        if message_id == "busy" and attempts[message_id] < 3:
            return httpx.Response(429, json={"error": {"message": "Rate limit"}})
        if message_id == "quota" and attempts[message_id] < 2:
            quota = {
                "message": "Quota exceeded for quota metric 'Queries'",
                "errors": [{"reason": "rateLimitExceeded"}],
            }
            return httpx.Response(403, json={"error": quota})
        if message_id == "gone":
            return httpx.Response(404, json={"error": {"message": "Not Found"}})
        labels = ["DRAFT"] if message_id == "draft" else ["INBOX", "SENT"]
        headers = [{"name": "Subject", "value": "Hi"}, {"name": "from", "value": "Bo <bo@x.com>"}]
        body = {
            "id": message_id,
            "threadId": "t",
            "labelIds": labels,
            "internalDate": "1761300000500",
            "payload": {"headers": headers},
        }
        return httpx.Response(200, json=body)

    ids = ["busy", "quota", "gone", "draft", "bad/id"]
    found = asyncio.run(http_api(handler).messages("token", ids, lambda done: None))

    assert [m.message_id for m in found] == ["busy", "quota"]
    assert found[0] == GmailMessage("busy", "t", Direction.OUTBOUND, "Bo <bo@x.com>", "Hi", "2025-10-24T10:00:00.5Z")
    assert attempts == {"busy": 3, "quota": 2, "gone": 1, "draft": 1}


def test_a_rate_limit_pauses_every_read_not_only_the_one_that_hit_it():
    events: list[str] = []

    async def record_wait(seconds: float) -> None:
        events.append("wait")

    def handler(request: httpx.Request) -> httpx.Response:
        message_id = request.url.path.rsplit("/", 1)[-1]
        events.append(message_id)
        if events.count(message_id) == 1 and message_id == "a":
            return httpx.Response(429, json={"error": {"message": "Rate limit"}})
        return httpx.Response(404, json={"error": {"message": "Not Found"}})

    api = GmailHttpApi(HttpsClient(transport=httpx.MockTransport(handler)), "https://gmail.example", sleep=record_wait)
    asyncio.run(api.messages("token", ["a", "b", "c"], lambda done: None))

    assert events[0] == "a"
    assert all(events[i - 1] == "wait" for i, event in enumerate(events) if i and event != "wait")


def test_a_failed_read_leaves_no_exception_unretrieved():
    async def read_all() -> list[dict]:
        unretrieved: list[dict] = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: unretrieved.append(context))
        api = http_api(lambda request: httpx.Response(400, json={"error": {"message": "Bad"}}))
        with pytest.raises(RemoteError):
            await api.messages("token", [f"m{n}" for n in range(30)], lambda done: None)
        gc.collect()
        return unretrieved

    assert asyncio.run(read_all()) == []


def test_history_that_gmail_no_longer_keeps_means_a_full_listing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})

    assert asyncio.run(http_api(handler).inbox_changes("token", "42")) is None


def test_trashing_a_thread_that_is_gone_counts_as_done():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/gmail/v1/users/me/threads/t1/trash"
        return httpx.Response(404, json={"error": {"message": "Not Found"}})

    asyncio.run(http_api(handler).trash_thread("token", "t1"))


class FakeAuthorization(Authorization):
    @property
    def configured(self) -> bool:
        return True

    async def sign_in(self, scopes, required):
        return Grant("access", "refresh")

    async def access_token(self, refresh_token):
        return "access"

    async def revoke(self, refresh_token):
        pass


class FakeApi(GmailApi):
    def __init__(self, inbox: list[GmailMessage], changes: tuple[list[str], str] | None = None):
        self.inbox, self.changes, self.sent, self.trashed = inbox, changes, [], []

    async def profile(self, token):
        return Profile("me@x.com", "100")

    async def inbox_ids(self, token):
        return [m.message_id for m in self.inbox]

    async def inbox_changes(self, token, history_id):
        return self.changes

    async def messages(self, token, ids, progress):
        return [m for m in self.inbox if m.message_id in ids]

    async def original(self, token, message_id):
        return RECEIVED

    async def send(self, token, thread_id, message):
        self.sent.append((thread_id, message))

    async def trash_thread(self, token, thread_id):
        pass

    async def trash_message(self, token, message_id):
        self.trashed.append(message_id)


def connector(tmp_path, api: FakeApi) -> tuple[Gmail, SqlcipherStateStore]:
    keyring = FileKeyring(tmp_path / "keyring.json")
    state = SqlcipherStateStore(SqlcipherDatabase(tmp_path / "silentdesk.db", keyring))
    app = Gmail(api, FakeAuthorization(), KeyringCredentials(keyring), state)
    asyncio.run(app.connect({}))
    return app, state


def test_a_full_sync_then_an_incremental_one(tmp_path):
    api = FakeApi([message("a", "t1", "2026-10-01T00:00:00Z"), message("b", "t2", "2026-10-02T00:00:00Z")])
    app, state = connector(tmp_path, api)

    first = asyncio.run(app.sync())
    assert sorted(t.key for t in first.topics) == ["t1", "t2"]
    assert asyncio.run(state.load()) == GmailState("me@x.com", "100")

    api.inbox.append(message("c", "t1", "2026-10-03T00:00:00Z"))
    api.changes = (["c"], "101")
    second = asyncio.run(app.sync())

    [thread] = second.topics
    assert (thread.key, [i.key for i in thread.items]) == ("t1", ["a", "c"])
    assert asyncio.run(state.load()).history_id == "101"


def test_a_sign_in_kept_from_legacy_syncs_and_finds_its_account(tmp_path):
    keyring = FileKeyring(tmp_path / "keyring.json")
    keyring.set(KeyringCredentials.NAME, "refresh")
    state = SqlcipherStateStore(SqlcipherDatabase(tmp_path / "silentdesk.db", keyring))
    app = Gmail(
        FakeApi([message("a", "t1", "2026-10-01T00:00:00Z")]), FakeAuthorization(), KeyringCredentials(keyring), state
    )

    assert [t.key for t in asyncio.run(app.sync()).topics] == ["t1"]
    assert asyncio.run(app.status()).account == "me@x.com"


def test_replying_answers_the_newest_message_of_a_synced_thread(tmp_path):
    api = FakeApi([message("a", "t1", "2026-10-01T00:00:00Z")])
    app, _ = connector(tmp_path, api)
    asyncio.run(app.sync())

    asyncio.run(app.reply("t1", "Thanks"))
    assert api.sent[0][0] == "t1"
    with pytest.raises(UnknownTopic):
        asyncio.run(app.reply("t9", "Thanks"))


def test_deleting_a_thread_forgets_its_messages(tmp_path):
    app, state = connector(tmp_path, FakeApi([message("a", "t1", "2026-10-01T00:00:00Z")]))
    asyncio.run(app.sync())
    asyncio.run(app.delete_topic("t1"))
    assert asyncio.run(state.threads()) == {}


def test_every_thread_and_message_is_deletable(tmp_path):
    app, _ = connector(tmp_path, FakeApi([message("a", "t1", "2026-10-01T00:00:00Z")]))
    [topic] = asyncio.run(app.sync()).topics
    assert topic.deletable and all(item.deletable for item in topic.items)


def test_deleting_one_message_trashes_it_and_forgets_only_it(tmp_path):
    api = FakeApi([message("a", "t1", "2026-10-01T00:00:00Z"), message("b", "t1", "2026-10-02T00:00:00Z")])
    app, state = connector(tmp_path, api)
    asyncio.run(app.sync())

    left = asyncio.run(app.delete_item("t1", "b"))

    assert api.trashed == ["b"]
    assert [m.message_id for m in asyncio.run(state.threads())["t1"]] == ["a"]
    assert [item.key for item in left.items] == ["a"]
    assert asyncio.run(app.delete_item("t1", "a")) is None


def test_a_thread_left_without_its_first_message_takes_the_next_ones_subject(tmp_path):
    first = message("a", "t1", "2026-10-01T00:00:00Z", "Invoice")
    second = message("b", "t1", "2026-10-02T00:00:00Z", "Re: Invoice")
    app, _ = connector(tmp_path, FakeApi([first, second]))
    asyncio.run(app.sync())

    assert asyncio.run(app.delete_item("t1", "a")).title == "Re: Invoice"


def test_trashing_a_message_posts_to_its_trash_and_a_gone_one_counts_as_done():
    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("POST", "/gmail/v1/users/me/messages/m1/trash")
        return httpx.Response(404, json={"error": {"message": "Not Found"}})

    asyncio.run(http_api(handler).trash_message("token", "m1"))


def test_an_unknown_error_status_is_a_remote_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=json.dumps({"error": {"message": "Bad"}}).encode())

    with pytest.raises(RemoteError, match="400: Bad"):
        asyncio.run(http_api(handler).profile("token"))
    with pytest.raises(AuthError):
        asyncio.run(http_api(lambda r: httpx.Response(401, json={})).profile("token"))
