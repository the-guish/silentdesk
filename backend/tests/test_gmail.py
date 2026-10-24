import asyncio
import base64
import json
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
import pytest

from silentdesk.core import errors
from silentdesk.core.model import Direction, GmailAccount, GmailMessage, Topic, VaultData, to_json
from silentdesk.core.ports import Config
from silentdesk.core.secret_names import GMAIL_REFRESH_TOKEN
from silentdesk.core.topics import topic_views
from silentdesk.sources.gmail import GmailSource, api, domain, oauth, reply, service
from silentdesk.sources.gmail.api import MessageMeta
from silentdesk.sources.gmail.reply import Original

from .fakes import FakeBrowser, make_host, mock_client

MODIFY = "https://www.googleapis.com/auth/gmail.modify"
SEND = "https://www.googleapis.com/auth/gmail.send"
CONFIG = Config(google_client_id="cid.apps.googleusercontent.com", google_client_secret="sec")


# --- domain (gmail/mod.rs) ------------------------------------------------


def meta(id: str, subject: str, date: str) -> MessageMeta:
    return MessageMeta(id, f"t-{id}", Direction.INBOUND, "", "", subject, date)


def test_each_email_gets_its_own_topic():
    data = VaultData()
    domain.add_messages(
        data, [meta("1", "Budget", "2026-10-23T10:00:00Z"), meta("2", "", "2026-10-22T10:00:00Z")], "now"
    )
    assert len(data.topics) == 2
    assert data.gmail_messages[0].topic_id != data.gmail_messages[1].topic_id
    views = topic_views(data)
    assert views[0]["title"] == "Budget"
    assert views[1]["title"] == "(no subject)"


def test_later_syncs_keep_what_is_stored():
    data = VaultData()
    domain.add_messages(data, [meta("1", "A", "d1"), meta("2", "B", "d2")], "now")
    topic_of_2 = data.gmail_messages[1].topic_id

    domain.add_messages(data, [meta("3", "C", "d3"), meta("2", "B2", "d2"), meta("3", "C", "d3")], "later")
    assert len(data.gmail_messages) == 3
    assert data.gmail_messages[1].topic_id == topic_of_2
    assert data.gmail_messages[1].subject == "B"
    assert [t.title for t in data.topics] == ["A", "B", "C"]


def test_new_ids_skips_stored_and_repeated():
    data = VaultData()
    domain.add_messages(data, [meta("1", "A", "d1")], "now")
    for ids, expected in [([], []), (["1"], []), (["2", "1", "3"], ["2", "3"]), (["2", "2"], ["2"])]:
        assert domain.new_ids(data, ids) == expected


def in_thread(id: str, thread: str, subject: str, date: str) -> MessageMeta:
    return MessageMeta(id, thread, Direction.INBOUND, "", "", subject, date)


def titles_by_thread(data: VaultData) -> dict[str, str]:
    titles = {t.id: t.title for t in data.topics}
    return {m.thread_id: titles[m.topic_id] for m in data.gmail_messages}


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        # A thread is one topic, titled by its newest subject.
        ([("1", "A", "Budget", "d1"), ("2", "A", "Re: Budget v2", "d2")], [], {"A": "Budget v2"}),
        ([("1", "A", "Budget", "d1"), ("2", "B", "Plans", "d2")], [], {"A": "Budget", "B": "Plans"}),
        # A later reply joins the topic and renames it.
        ([("1", "A", "Budget", "d1")], [("2", "A", "RE: New budget", "d2")], {"A": "New budget"}),
        # An older message arriving later keeps the newest title.
        ([("2", "A", "Second", "d2")], [("1", "A", "First", "d1")], {"A": "Second"}),
        ([("1", "A", "", "d1")], [], {"A": "(no subject)"}),
        ([("1", "A", "Re:", "d1")], [], {"A": "(no subject)"}),
    ],
)
def test_groups_messages_by_thread(first, second, expected):
    data = VaultData()
    domain.add_messages(data, [in_thread(*m) for m in first], "now")
    topic_ids = {m.thread_id: m.topic_id for m in data.gmail_messages}
    domain.add_messages(data, [in_thread(*m) for m in second], "later")
    assert titles_by_thread(data) == expected
    assert len(data.topics) == len(expected)
    # A thread keeps its topic.
    assert all(m.topic_id == topic_ids[m.thread_id] for m in data.gmail_messages if m.thread_id in topic_ids)


@pytest.mark.parametrize(
    ("subject", "title"),
    [
        ("Budget", "Budget"),
        ("Re: Budget", "Budget"),
        ("RE: Fwd: re:Budget", "Budget"),
        ("Re[2]: Budget", "Budget"),
        ("FW: AW: SV: TR: Budget", "Budget"),
        ("Fwd : Budget", "Budget"),
        ("Regarding: Budget", "Regarding: Budget"),
        ("Budget Re: plan", "Budget Re: plan"),
        ("  ", "(no subject)"),
    ],
)
def test_thread_titles_drop_reply_prefixes(subject, title):
    assert domain.thread_title(subject) == title


def test_merges_topics_stored_one_per_message():
    # Before threads, each message had a topic of its own.
    data = VaultData(
        topics=[Topic("t1", "Budget", "then"), Topic("t2", "Re: Budget", "then"), Topic("t3", "Plans", "then")],
        gmail_messages=[
            GmailMessage("1", "A", "t1", Direction.INBOUND, "", "", "Budget", "d1"),
            GmailMessage("2", "A", "t2", Direction.INBOUND, "", "", "Re: Budget", "d2"),
            GmailMessage("3", "B", "t3", Direction.INBOUND, "", "", "Plans", "d3"),
        ],
    )
    domain.group_threads(data)
    assert [(t.id, t.title) for t in data.topics] == [("t1", "Budget"), ("t3", "Plans")]
    assert [m.topic_id for m in data.gmail_messages] == ["t1", "t1", "t3"]


def test_remove_thread_drops_its_messages_and_topic():
    data = VaultData()
    domain.add_messages(
        data, [in_thread("1", "A", "A", "d1"), in_thread("2", "A", "A", "d2"), in_thread("3", "B", "B", "d3")], "now"
    )
    domain.remove_thread(data, "A")
    domain.remove_thread(data, "unknown")
    assert [m.message_id for m in data.gmail_messages] == ["3"]
    assert [t.title for t in data.topics] == ["B"]


def test_clear_gmail_removes_everything():
    data = VaultData()
    domain.add_messages(data, [meta("1", "A", "d1")], "now")
    data.gmail_history_id = "42"
    domain.clear(data)
    assert data.topics == []
    assert data.gmail_messages == []
    assert data.gmail_history_id is None


# --- oauth (gmail/oauth.rs) -----------------------------------------------


def test_authorization_url_has_required_parameters():
    client = oauth.OAuthClient("abc.apps.googleusercontent.com", None)
    url = oauth.authorization_url(client, oauth.GMAIL, "http://127.0.0.1:5000", "chal", "st")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    q = dict(parse_qsl(urlsplit(url).query))
    assert q["client_id"] == "abc.apps.googleusercontent.com"
    assert q["redirect_uri"] == "http://127.0.0.1:5000"
    assert q["scope"] == f"{MODIFY} {SEND}"
    assert q["code_challenge_method"] == "S256"
    assert q["state"] == "st"
    assert q["access_type"] == "offline"
    assert q["prompt"] == "consent"


def test_client_from_config():
    assert oauth.OAuthClient.from_config(Config()) is None
    assert oauth.OAuthClient.from_config(Config(google_client_id="  ")) is None
    assert oauth.OAuthClient.from_config(Config(google_client_id="id", google_client_secret="")) == oauth.OAuthClient(
        "id", None
    )


def token_failure(status: int, body) -> Exception:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body) if not isinstance(body, str) else httpx.Response(status, text=body)

    async def run():
        async with mock_client(handler) as http:
            try:
                await oauth.access_token(http, oauth.OAuthClient("id"), oauth.GMAIL, "rt")
            except errors.AppError as e:
                return e

    return asyncio.run(run())


def test_token_errors():
    assert isinstance(token_failure(400, {"error": "invalid_grant"}), errors.Reauthorize)
    assert token_failure(400, {"error": "invalid_grant"}).message == (
        "Gmail access was revoked or has expired. Connect again."
    )
    assert "SILENTDESK_GOOGLE_CLIENT_SECRET" in token_failure(401, {"error": "invalid_client"}).message
    assert token_failure(400, {"error": "invalid_request"}).message == (
        "Sign-in failed: Google returned invalid_request (400)."
    )
    assert token_failure(502, "<html>").message == "Sign-in failed: Google returned unknown_error (502)."
    assert isinstance(token_failure(200, {"token_type": "Bearer"}), errors.Network)


# --- api (gmail/api.rs) ---------------------------------------------------


def raw(text: str) -> api.RawMessage:
    return api._raw_message(json.loads(text))


def test_parses_inbound_message():
    m = api.to_meta(
        raw("""{
            "id": "18c1", "threadId": "18c0", "labelIds": ["INBOX", "UNREAD"],
            "internalDate": "1761213600000",
            "payload": { "headers": [
                {"name": "From", "value": "Ana Ruiz <ana@example.com>"},
                {"name": "To", "value": "me@example.com"},
                {"name": "subject", "value": " Q4 budget "}
            ]}
        }""")
    )
    assert m.direction == Direction.INBOUND
    assert m.from_ == "Ana Ruiz <ana@example.com>"
    assert m.subject == "Q4 budget"
    assert m.date == "2025-10-23T10:00:00Z"
    assert m.thread_id == "18c0"


def test_sent_label_means_outbound():
    m = api.to_meta(raw('{"id":"a","threadId":"b","labelIds":["SENT"],"internalDate":"0"}'))
    assert m.direction == Direction.OUTBOUND
    assert m.subject == ""


def test_skips_drafts_and_chats():
    assert api.to_meta(raw('{"id":"a","threadId":"b","labelIds":["DRAFT"],"internalDate":"0"}')) is None
    assert api.to_meta(raw('{"id":"a","threadId":"b","labelIds":["CHAT"],"internalDate":"0"}')) is None


def test_internal_dates():
    assert api.rfc3339_from_millis("1761213600123") == "2025-10-23T10:00:00.123Z"
    assert api.rfc3339_from_millis("1761213600120") == "2025-10-23T10:00:00.12Z"
    assert api.rfc3339_from_millis("0") == "1970-01-01T00:00:00Z"
    assert api.rfc3339_from_millis(None) is None
    assert api.rfc3339_from_millis("1_000") is None
    assert api.rfc3339_from_millis("99999999999999999999") is None
    assert api.to_meta(raw('{"id":"a","threadId":"b"}')) is None


def test_reads_reply_headers():
    o = api.to_original(
        raw("""{
            "id": "18c1", "threadId": "18c0", "labelIds": ["INBOX"],
            "payload": { "headers": [
                {"name": "From", "value": "Ana <ana@example.com>"},
                {"name": "Reply-To", "value": "list@example.com"},
                {"name": "Message-Id", "value": "<m1@example.com>"},
                {"name": "References", "value": "<m0@example.com>"}
            ]}
        }""")
    )
    assert o.direction == Direction.INBOUND
    assert o.reply_to == "list@example.com"
    assert o.message_id == "<m1@example.com>"
    assert o.references == "<m0@example.com>"
    assert o.subject == ""


def test_inbox_additions_keep_inbox_messages_once():
    listing = api._history_list(
        json.loads("""{"historyId": "9", "history": [
            {"messagesAdded": [
                {"message": {"id": "a", "labelIds": ["INBOX", "UNREAD"]}},
                {"message": {"id": "sent", "labelIds": ["SENT"]}}
            ]},
            {"labelsAdded": [
                {"message": {"id": "b", "labelIds": ["INBOX"]}, "labelIds": ["INBOX"]},
                {"message": {"id": "starred", "labelIds": ["STARRED"]}, "labelIds": ["STARRED"]}
            ]},
            {"messagesAdded": [{"message": {"id": "a", "labelIds": ["INBOX"]}}]},
            {}
        ]}""")
    )
    assert api.inbox_additions(listing.history) == ["a", "b"]


def test_transient_errors():
    def a(status, message):
        return errors.Api("Gmail", status, message)

    for error, expected in [
        (a(429, "Too many requests"), True),
        (a(503, "Backend error"), True),
        (a(403, "User-rate limit exceeded"), True),
        (a(403, "Rate Limit Exceeded"), True),
        (a(403, "Forbidden"), False),
        (a(404, "Not Found"), False),
        (a(400, "Invalid"), False),
        (errors.Reauthorize("Gmail"), False),
    ]:
        assert api.is_transient(error) == expected, error.message


def test_rejects_unexpected_ids():
    assert api.is_gmail_id("18c1a2b3")
    assert not api.is_gmail_id("../profile")
    assert not api.is_gmail_id("")
    assert not api.is_gmail_id("abc\n")
    assert not api.is_gmail_id("ab٣")


# --- reply (gmail/reply.rs) -----------------------------------------------


def original(direction: Direction, reply_to: str) -> Original:
    return Original(
        direction=direction,
        from_="Ana <ana@example.com>",
        to="me@example.com, bo@example.com",
        reply_to=reply_to,
        subject="Budget",
        message_id="<m1@example.com>",
        references="<m0@example.com>",
    )


def test_recipient_by_direction():
    for direction, reply_to, expected in [
        (Direction.INBOUND, "", "Ana <ana@example.com>"),
        (Direction.INBOUND, "  ", "Ana <ana@example.com>"),
        (Direction.INBOUND, "list@example.com", "list@example.com"),
        (Direction.OUTBOUND, "", "me@example.com, bo@example.com"),
        (Direction.OUTBOUND, "list@example.com", "me@example.com, bo@example.com"),
    ]:
        assert reply.recipient(original(direction, reply_to)) == expected


def test_subject_prefix():
    for given, expected in [
        ("Budget", "Re: Budget"),
        ("  Budget ", "Re: Budget"),
        ("Re: Budget", "Re: Budget"),
        ("RE:Budget", "RE:Budget"),
        ("Ré", "Re: Ré"),
        ("", "Re:"),
    ]:
        assert reply.subject(given) == expected, given


def test_clean_and_encode_headers():
    for given, expected in [("plain", "plain"), ("a\r\nBcc: x@evil.com", "a Bcc: x@evil.com"), ("a\n\nb", "a b")]:
        assert reply.clean(given) == expected
    assert reply.encode_word("Re: hi") == "Re: hi"
    assert reply.encode_word("Re: ¿sí?") == "=?UTF-8?B?UmU6IMK/c8OtPw==?="


def test_builds_threaded_reply():
    message = reply.build(original(Direction.INBOUND, ""), "Thanks!\nAna")
    head, body = message.split("\r\n\r\n", 1)
    assert head == (
        "To: Ana <ana@example.com>\r\n"
        "Subject: Re: Budget\r\n"
        "In-Reply-To: <m1@example.com>\r\n"
        "References: <m0@example.com> <m1@example.com>\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=UTF-8\r\n"
        "Content-Transfer-Encoding: base64"
    )
    assert base64.b64decode(body.replace("\r\n", "")) == b"Thanks!\r\nAna"


def test_long_bodies_wrap_at_76():
    lines = reply.build(original(Direction.INBOUND, ""), "x" * 200).split("\r\n\r\n", 1)[1].split("\r\n")
    assert [len(line) for line in lines] == [76, 76, 76, 40, 0]


def test_no_threading_headers_without_message_id():
    o = original(Direction.INBOUND, "")
    o.message_id = ""
    message = reply.build(o, "x")
    assert "In-Reply-To" not in message
    assert "References" not in message


def test_injected_recipient_stays_one_header():
    o = original(Direction.INBOUND, "")
    o.from_ = "a@example.com\r\nBcc: x@evil.com"
    assert reply.build(o, "x").startswith("To: a@example.com Bcc: x@evil.com\r\nSubject:")


# --- service (commands/gmail.rs) ------------------------------------------


GMAIL = "/gmail/v1/users/me"


class FakeGoogle:
    """Google's token endpoint and the Gmail API, enough for the service."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_error: dict | None = None
        self.scope = f"{MODIFY} {SEND}"
        self.refresh_token = "rt-new"
        self.email = "me@example.com"
        self.history_id = "500"
        self.inbox: list[str] = []
        # id -> message JSON, or an int status.
        self.messages: dict[str, dict | int] = {}
        self.history: dict | int = 404
        self.trash_status = 200
        # thread id -> message JSONs.
        self.threads: dict[str, list[dict]] = {}
        # Statuses to answer before the real reply, per path.
        self.failures: dict[str, list[int]] = {}

    def paths(self, prefix: str = "") -> list[str]:
        return [r.url.path for r in self.requests if r.url.path.startswith(prefix)]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if host == "oauth2.googleapis.com" and path == "/token":
            form = parse_qs(request.content.decode())
            if self.token_error is not None:
                return httpx.Response(400, json=self.token_error)
            if form["grant_type"] == ["authorization_code"]:
                assert form["code"] == ["the-code"] and form["code_verifier"][0]
                assert form["client_secret"] == ["sec"]
                return httpx.Response(
                    200, json={"access_token": "at", "refresh_token": self.refresh_token, "scope": self.scope}
                )
            assert form["refresh_token"][0]
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3599})
        if host == "oauth2.googleapis.com" and path == "/revoke":
            return httpx.Response(200)
        assert host == "gmail.googleapis.com"
        assert request.headers["authorization"] == "Bearer at"
        pending = self.failures.get(path)
        if pending:
            return httpx.Response(pending.pop(0), json={"error": {"message": "Backend error"}})
        if path == f"{GMAIL}/profile":
            return httpx.Response(200, json={"emailAddress": self.email, "historyId": self.history_id})
        if path == f"{GMAIL}/messages":
            params = request.url.params
            assert params["labelIds"] == "INBOX" and params["maxResults"] == "500"
            # Two pages, to exercise paging.
            if "pageToken" not in params:
                half = len(self.inbox) // 2
                return httpx.Response(
                    200, json={"messages": [{"id": i} for i in self.inbox[:half]], "nextPageToken": "p2"}
                )
            return httpx.Response(200, json={"messages": [{"id": i} for i in self.inbox[len(self.inbox) // 2 :]]})
        if path == f"{GMAIL}/history":
            if isinstance(self.history, int):
                return httpx.Response(self.history, json={"error": {"message": "Requested entity was not found."}})
            return httpx.Response(200, json=self.history)
        if path == f"{GMAIL}/messages/send":
            return httpx.Response(200, json={"id": "sent1"})
        if path.endswith("/trash"):
            if self.trash_status == 403:
                return httpx.Response(
                    403, json={"error": {"message": "Request had insufficient authentication scopes."}}
                )
            return httpx.Response(self.trash_status, json={})
        if path.startswith(f"{GMAIL}/threads/"):
            params = request.url.params
            assert (params["format"], params.get_list("metadataHeaders")) == ("metadata", ["From"])
            found = self.threads.get(path.rsplit("/", 1)[1])
            if found is None:
                return httpx.Response(404, json={"error": {"message": "Not Found"}})
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[1], "messages": found})
        if path.startswith(f"{GMAIL}/messages/"):
            found = self.messages.get(path.rsplit("/", 1)[1], 404)
            if isinstance(found, int):
                return httpx.Response(found, json={"error": {"message": "Not Found"}})
            return httpx.Response(200, json=found)
        raise AssertionError(f"unexpected request {request.method} {request.url}")


def message(id: str, subject: str = "", labels=("INBOX",), date: str = "1761213600000") -> dict:
    return {
        "id": id,
        "threadId": f"t-{id}",
        "labelIds": list(labels),
        "internalDate": date,
        "payload": {"headers": [{"name": "Subject", "value": subject}]},
    }


async def _get(port: int, path: str) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    await writer.drain()
    response = await reader.read()
    writer.close()
    return response


def redirecting_browser(code: str = "the-code") -> FakeBrowser:
    """A browser that signs in at once: Google redirects back to the loopback
    listener with `code` and the request's state."""

    def on_open(url: str) -> None:
        q = dict(parse_qsl(urlsplit(url).query))
        port = int(q["redirect_uri"].rsplit(":", 1)[1])

        async def redirect():
            # The listener answers once it knows the state to expect.
            await asyncio.sleep(0.05)
            await _get(port, f"/?code={code}&state={q['state']}")

        asyncio.get_running_loop().create_task(redirect())

    return FakeBrowser(on_open)


def connected(**data) -> VaultData:
    return VaultData(gmail_account=GmailAccount("me@example.com"), **data)


def setup(data: VaultData | None = None, secrets=None, browser=None, config=CONFIG):
    google = FakeGoogle()
    host = make_host(data, secrets if secrets is not None else {GMAIL_REFRESH_TOKEN: "rt"}, config, browser)
    return google, host, GmailSource(host, mock_client(google.handler))


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    waits: list[float] = []

    async def no_wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr(api, "READ_PACE", 0.0)
    monkeypatch.setattr(api, "sleep", no_wait)
    return waits


def test_status():
    async def run():
        _, _, source = setup(config=Config())
        assert await source.status() == service.ServiceStatus(False, False, None)
        _, _, source = setup(connected())
        assert await source.status() == service.ServiceStatus(True, True, "me@example.com")
        _, _, source = setup(connected(), secrets={})
        assert await source.status() == service.ServiceStatus(True, False, "me@example.com")

    asyncio.run(run())


def test_methods_are_named_for_the_ui():
    _, _, source = setup()
    assert set(source.methods()) == {
        "gmail.status",
        "gmail.connect",
        "gmail.sync",
        "gmail.disconnect",
        "gmail.trash",
        "gmail.reply",
        "gmail.thread",
    }


def test_not_configured_and_not_connected():
    async def run():
        _, _, source = setup(config=Config())
        with pytest.raises(errors.NotConfigured) as e:
            await source.sync()
        assert e.value.message == (
            "Gmail is not set up. Set SILENTDESK_GOOGLE_CLIENT_ID in .env (see docs/setup/gmail.md)."
        )
        _, _, source = setup()
        with pytest.raises(errors.NotConnected):
            await source.sync()
        _, _, source = setup(connected(), secrets={})
        with pytest.raises(errors.NotConnected):
            await source.sync()

    asyncio.run(run())


def test_connect_signs_in_and_stores_the_token():
    async def run():
        browser = redirecting_browser()
        google, host, source = setup(secrets={}, browser=browser)
        status = await source.methods()["gmail.connect"]({})
        assert status == service.ServiceStatus(True, True, "me@example.com")
        assert host.secrets.get(GMAIL_REFRESH_TOKEN) == "rt-new"
        assert host.store.data().gmail_account == GmailAccount("me@example.com")
        (url,) = browser.opened
        q = dict(parse_qsl(urlsplit(url).query))
        assert q["client_id"] == CONFIG.google_client_id and q["code_challenge_method"] == "S256"
        assert "/revoke" not in google.paths()

    asyncio.run(run())


def test_reconnecting_another_account_revokes_and_clears():
    async def run():
        stored = connected(
            topics=[Topic("t1", "Old", "now")],
            gmail_messages=[GmailMessage("a", "ta", "t1", Direction.INBOUND, "", "", "Old", "d")],
            gmail_history_id="9",
        )
        stored.gmail_account = GmailAccount("old@example.com")
        google, host, source = setup(stored, browser=redirecting_browser())
        await source.connect({})
        revoke = next(r for r in google.requests if r.url.path == "/revoke")
        assert parse_qs(revoke.content.decode()) == {"token": ["rt"]}
        data = host.store.data()
        assert data.gmail_account == GmailAccount("me@example.com")
        assert data.topics == [] and data.gmail_messages == [] and data.gmail_history_id is None

    asyncio.run(run())


def test_reconnecting_the_same_account_keeps_topics():
    async def run():
        stored = connected(
            topics=[Topic("t1", "Old", "now")],
            gmail_messages=[GmailMessage("a", "ta", "t1", Direction.INBOUND, "", "", "Old", "d")],
        )
        _, host, source = setup(stored, browser=redirecting_browser())
        await source.connect({})
        assert [t.id for t in host.store.data().topics] == ["t1"]

    asyncio.run(run())


def test_connect_without_the_scopes_stores_nothing():
    async def run():
        google, host, source = setup(secrets={}, browser=redirecting_browser())
        google.scope = MODIFY
        with pytest.raises(errors.Auth) as e:
            await source.connect({})
        assert e.value.message == "Sign-in failed: Gmail access was not granted."
        assert host.secrets.get(GMAIL_REFRESH_TOKEN) is None
        assert host.store.data().gmail_account is None

    asyncio.run(run())


def test_connect_when_the_browser_cannot_open():
    class Broken:
        async def open(self, url):
            raise errors.Host("no opener")

    async def run():
        _, _, source = setup(secrets={}, browser=Broken())
        with pytest.raises(errors.Auth) as e:
            await source.connect({})
        assert e.value.message == "Sign-in failed: could not open your web browser."

    asyncio.run(run())


def test_first_sync_reads_the_inbox_in_batches(monkeypatch):
    monkeypatch.setattr(service, "SAVE_EVERY", 2)
    monkeypatch.setattr(service, "PROGRESS_EVERY", 2)

    async def run():
        google, host, source = setup(connected())
        google.inbox = ["m1", "m2", "m3", "m4", "m5", "m1"]
        google.messages = {
            "m1": message("m1", "One"),
            "m2": message("m2", "", labels=("DRAFT",)),
            "m3": message("m3", "Three", labels=("SENT",)),
            # m4 was deleted in the meantime.
            "m5": message("m5", "Five", date="1761213700000"),
        }
        writes = host.store.writes
        views = await source.sync()

        assert [v["title"] for v in views] == ["Five", "One", "Three"]
        data = host.store.data()
        assert {m.message_id: m.direction for m in data.gmail_messages} == {
            "m1": Direction.INBOUND,
            "m3": Direction.OUTBOUND,
            "m5": Direction.INBOUND,
        }
        assert data.gmail_history_id == "500"
        # Three batches, then the history ID.
        assert host.store.writes - writes == 4
        progress = [p for e, p in host.events.events if e == "gmail-sync-progress"]
        assert [p["done"] for p in progress] == [0, 2, 2, 4, 4, 5]
        assert {p["total"] for p in progress} == {5}
        # A fresh access token per batch.
        assert google.paths().count("/token") == 4
        # The marker is taken before listing.
        assert google.paths(GMAIL)[:2] == [f"{GMAIL}/profile", f"{GMAIL}/messages"]
        read = next(r for r in google.requests if r.url.path == f"{GMAIL}/messages/m1")
        assert read.url.params.multi_items() == [("format", "metadata"), ("metadataHeaders", "Subject")]

    asyncio.run(run())


def test_later_syncs_list_history_only():
    async def run():
        stored = connected(
            topics=[Topic("t1", "A", "now")],
            gmail_messages=[GmailMessage("a", "ta", "t1", Direction.INBOUND, "", "", "A", "d")],
            gmail_history_id="100",
        )
        google, host, source = setup(stored)
        google.history = {
            "historyId": "200",
            "history": [
                {"messagesAdded": [{"message": {"id": "c", "labelIds": ["INBOX"]}}]},
                {"labelsAdded": [{"message": {"id": "a", "labelIds": ["INBOX"]}, "labelIds": ["INBOX"]}]},
            ],
        }
        google.messages = {"c": message("c", "New")}
        await source.sync()

        assert f"{GMAIL}/profile" not in google.paths()
        assert f"{GMAIL}/messages/a" not in google.paths()
        history = next(r for r in google.requests if r.url.path == f"{GMAIL}/history")
        assert history.url.params.multi_items() == [
            ("startHistoryId", "100"),
            ("labelId", "INBOX"),
            ("historyTypes", "messageAdded"),
            ("historyTypes", "labelAdded"),
        ]
        data = host.store.data()
        assert data.gmail_history_id == "200"
        assert [m.message_id for m in data.gmail_messages] == ["a", "c"]

    asyncio.run(run())


def test_a_sync_with_nothing_new_still_groups_threads():
    async def run():
        stored = connected(
            topics=[Topic("t1", "A", "then"), Topic("t2", "Re: A", "then")],
            gmail_messages=[
                GmailMessage("a", "ta", "t1", Direction.INBOUND, "", "", "A", "d1"),
                GmailMessage("b", "ta", "t2", Direction.INBOUND, "", "", "Re: A", "d2"),
            ],
            gmail_history_id="100",
        )
        google, host, source = setup(stored)
        google.history = {"historyId": "200", "history": []}
        views = await source.sync()
        assert [(v["id"], v["title"], len(v["emails"])) for v in views] == [("t1", "A", 2)]

    asyncio.run(run())


def test_expired_history_lists_the_whole_inbox_again():
    async def run():
        google, host, source = setup(connected(gmail_history_id="1"))
        google.history = 404
        google.inbox = ["m1"]
        google.messages = {"m1": message("m1", "One")}
        await source.sync()
        assert f"{GMAIL}/profile" in google.paths()
        assert host.store.data().gmail_history_id == "500"

    asyncio.run(run())


def test_transient_errors_are_retried(fast):
    async def run():
        google, host, source = setup(connected())
        google.inbox = ["m1"]
        google.messages = {"m1": message("m1", "One")}
        google.failures[f"{GMAIL}/messages/m1"] = [503, 429]
        await source.sync()
        assert fast == [1, 2]
        assert len(host.store.data().gmail_messages) == 1

        google.failures[f"{GMAIL}/profile"] = [503] * 6
        fast.clear()
        with pytest.raises(errors.Api) as e:
            await api.profile(source.http, "at")
        assert fast == [1, 2, 4, 8, 16]
        assert e.value.message == "Gmail API error (503): Backend error"

    asyncio.run(run())


def test_a_failed_read_fails_the_sync_and_keeps_the_marker():
    async def run():
        google, host, source = setup(connected())
        google.inbox = ["m1", "m2"]
        google.messages = {"m1": message("m1"), "m2": 400}
        with pytest.raises(errors.Api):
            await source.sync()
        assert host.store.data().gmail_history_id is None

    asyncio.run(run())


def test_dead_grant_deletes_the_token_and_keeps_topics():
    async def run():
        stored = connected(
            topics=[Topic("t1", "A", "now")],
            gmail_messages=[GmailMessage("a", "ta", "t1", Direction.INBOUND, "", "", "A", "d")],
        )
        google, host, source = setup(stored)
        google.token_error = {"error": "invalid_grant"}
        with pytest.raises(errors.Reauthorize) as e:
            await source.sync()
        assert e.value.message == "Gmail access was revoked or has expired. Connect again."
        assert host.secrets.get(GMAIL_REFRESH_TOKEN) is None
        assert [t.id for t in host.store.data().topics] == ["t1"]
        assert host.store.data().gmail_account == GmailAccount("me@example.com")
        assert (await source.status()).connected is False

    asyncio.run(run())


def test_api_401_asks_to_reconnect():
    async def run():
        google, _, source = setup(connected())
        google.failures[f"{GMAIL}/profile"] = [401]
        with pytest.raises(errors.Reauthorize):
            await source.sync()

    asyncio.run(run())


def stored_message() -> VaultData:
    return connected(
        topics=[Topic("t1", "A", "now"), Topic("t2", "B", "now")],
        gmail_messages=[
            GmailMessage("a1", "ta", "t1", Direction.INBOUND, "", "", "A", "d1"),
            GmailMessage("b2", "tb", "t2", Direction.INBOUND, "", "", "B", "d2"),
        ],
    )


def test_trash_drops_the_thread_and_its_topic():
    async def run():
        data = stored_message()
        data.gmail_messages.append(GmailMessage("a3", "ta", "t1", Direction.INBOUND, "", "", "Re: A", "d3"))
        google, host, source = setup(data)
        views = await source.methods()["gmail.trash"]({"messageId": "a1"})
        assert [v["id"] for v in views] == ["t2"]
        post = next(r for r in google.requests if r.url.path.endswith("/trash"))
        assert post.method == "POST" and post.url.path == f"{GMAIL}/threads/ta/trash"
        assert json.loads(post.content) == {}
        assert [m.message_id for m in host.store.data().gmail_messages] == ["b2"]

        # Already gone in Gmail: still trashed here.
        google.trash_status = 404
        views = await source.trash({"messageId": "b2"})
        assert views == []

    asyncio.run(run())


def test_thread_reads_the_messages_live():
    async def run():
        google, host, source = setup(stored_message())

        def sent(id, sender, snippet, date, labels=("INBOX",)):
            return {
                "id": id,
                "threadId": "ta",
                "labelIds": list(labels),
                "internalDate": date,
                "snippet": snippet,
                "payload": {"headers": [{"name": "From", "value": sender}]},
            }

        google.threads["ta"] = [
            sent("a2", "me@example.com", "Sure, see you", "1761213700000", ("SENT",)),
            sent("a1", '"Ana Ruiz" <ana@x.com>', "Can we meet &amp; talk?", "1761213600000"),
            sent("d1", "me@example.com", "draft", "1761213800000", ("DRAFT",)),
        ]
        writes = host.store.writes
        messages = to_json(await source.methods()["gmail.thread"]({"topicId": "t1"}))
        assert [(m["id"], m["author"], m["direction"], m["text"]) for m in messages] == [
            ("a1", "Ana Ruiz", "inbound", "Can we meet & talk?"),
            ("a2", "me@example.com", "outbound", "Sure, see you"),
        ]
        assert messages[0]["date"] == "2025-10-23T10:00:00Z"
        # Read live, never stored.
        assert host.store.writes == writes

        # A thread deleted in Gmail has no messages.
        assert await source.thread({"topicId": "t2"}) == []
        with pytest.raises(errors.AppError) as e:
            await source.thread({"topicId": "gone"})
        assert "no Gmail thread" in e.value.message

    asyncio.run(run())


def test_trash_only_known_messages():
    async def run():
        google, _, source = setup(stored_message())
        with pytest.raises(errors.UnknownMessage):
            await source.trash({"messageId": "zz"})
        assert google.requests == []

    asyncio.run(run())


def test_trash_without_the_new_scopes():
    async def run():
        google, host, source = setup(stored_message())
        google.trash_status = 403
        with pytest.raises(errors.MissingPermission) as e:
            await source.trash({"messageId": "a1"})
        assert e.value.message == "Gmail needs new permissions. Disconnect, then connect again."
        assert len(host.store.data().gmail_messages) == 2

    asyncio.run(run())


def test_reply_sends_in_the_thread():
    async def run():
        google, _, source = setup(stored_message())
        google.messages = {
            "a1": {
                "id": "a1",
                "threadId": "ta",
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Ana <ana@example.com>"},
                        {"name": "Subject", "value": "Budget"},
                        {"name": "Message-ID", "value": "<m1@example.com>"},
                    ]
                },
            }
        }
        assert await source.methods()["gmail.reply"]({"messageId": "a1", "body": "Thanks!"}) is None
        read = next(r for r in google.requests if r.url.path == f"{GMAIL}/messages/a1")
        assert [v for k, v in read.url.params.multi_items() if k == "metadataHeaders"] == [
            "From",
            "To",
            "Reply-To",
            "Subject",
            "Message-ID",
            "References",
        ]
        sent = next(r for r in google.requests if r.url.path == f"{GMAIL}/messages/send")
        body = json.loads(sent.content)
        assert body["threadId"] == "ta"
        raw_message = base64.urlsafe_b64decode(body["raw"]).decode()
        assert raw_message.startswith(
            "To: Ana <ana@example.com>\r\nSubject: Re: Budget\r\nIn-Reply-To: <m1@example.com>\r\n"
        )

    asyncio.run(run())


def test_reply_needs_a_body_and_a_known_message():
    async def run():
        google, _, source = setup(stored_message())
        with pytest.raises(errors.EmptyReply):
            await source.reply({"messageId": "a1", "body": " \n "})
        with pytest.raises(errors.UnknownMessage):
            await source.reply({"messageId": "zz", "body": "Hi"})
        with pytest.raises(errors.AppError):
            await source.reply({"messageId": "a1"})
        assert google.requests == []

    asyncio.run(run())


def test_actions_wait_for_the_running_operation():
    async def run():
        _, _, source = setup(stored_message())
        async with source.op:
            trash = asyncio.create_task(source.trash({"messageId": "a1"}))
            await asyncio.sleep(0.01)
            assert not trash.done()
        assert [v["id"] for v in await trash] == ["t2"]

    asyncio.run(run())


def test_disconnect_revokes_and_forgets_everything():
    async def run():
        google, host, source = setup(stored_message())
        status = await source.methods()["gmail.disconnect"]({})
        assert status == service.ServiceStatus(True, False, None)
        revoke = next(r for r in google.requests if r.url.path == "/revoke")
        assert parse_qs(revoke.content.decode()) == {"token": ["rt"]}
        assert host.secrets.get(GMAIL_REFRESH_TOKEN) is None
        data = host.store.data()
        assert data.topics == [] and data.gmail_messages == [] and data.gmail_account is None

    asyncio.run(run())


def test_disconnect_survives_a_failed_revoke():
    def offline(request):
        raise httpx.ConnectError("offline")

    async def run():
        host = make_host(stored_message(), {GMAIL_REFRESH_TOKEN: "rt"}, CONFIG)
        source = GmailSource(host, mock_client(offline))
        assert (await source.disconnect()).connected is False
        assert host.secrets.get(GMAIL_REFRESH_TOKEN) is None

    asyncio.run(run())
