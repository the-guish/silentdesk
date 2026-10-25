"""The Gmail connector: replies, threads, its HTTP adapter and its syncs."""

from __future__ import annotations

import asyncio
import base64
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

    found = asyncio.run(http_api(handler).messages("token", ["busy", "gone", "draft", "bad/id"], lambda done: None))

    assert found == [GmailMessage("busy", "t", Direction.OUTBOUND, "Bo <bo@x.com>", "Hi", "2025-10-24T10:00:00.5Z")]
    assert attempts == {"busy": 3, "gone": 1, "draft": 1}


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
        self.inbox, self.changes, self.sent = inbox, changes, []

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


def test_an_unknown_error_status_is_a_remote_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=json.dumps({"error": {"message": "Bad"}}).encode())

    with pytest.raises(RemoteError, match="400: Bad"):
        asyncio.run(http_api(handler).profile("token"))
    with pytest.raises(AuthError):
        asyncio.run(http_api(lambda r: httpx.Response(401, json={})).profile("token"))
