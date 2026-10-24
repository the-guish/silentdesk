import asyncio
import json
import socket
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
import pytest

from silentdesk.core import errors
from silentdesk.core.model import (
    Direction,
    GmailMessage,
    SlackAccount,
    SlackMessage,
    Topic,
    VaultData,
)
from silentdesk.core.ports import Config
from silentdesk.core.secret_names import SLACK_CREDENTIAL
from silentdesk.core.topics import new_topic, prune_topics
from silentdesk.sources.base import ServiceStatus
from silentdesk.sources.slack import SlackSource, api, domain, oauth
from silentdesk.sources.slack.api import Match, MessageMeta
from silentdesk.sources.slack.oauth import AccessResponse, Credential

from .fakes import FakeBrowser, make_host, mock_client

# --- domain (slack/mod.rs) ------------------------------------------------


def meta(channel: str, ts: str, preview: str) -> MessageMeta:
    return MessageMeta(
        channel_id=channel,
        ts=ts,
        direction=Direction.INBOUND,
        author="Ana",
        counterpart="Ana",
        preview=preview,
        permalink="https://acme.slack.com/archives/D1/p1",
        date="2026-10-23T10:00:00Z",
    )


def test_each_message_gets_its_own_topic():
    data = VaultData()
    domain.apply_sync(data, [meta("D1", "1.0", "Can you review?"), meta("D1", "2.0", "")], "now")
    assert len(data.topics) == 2
    assert [t.title for t in data.topics] == ["Can you review?", "(empty message)"]


def test_resync_keeps_topics_and_drops_old_ones():
    data = VaultData()
    domain.apply_sync(data, [meta("D1", "1.0", "A"), meta("D2", "2.0", "B")], "now")
    topic_of_b = data.slack_messages[1].topic_id
    domain.apply_sync(data, [meta("D3", "3.0", "C"), meta("D2", "2.0", "B")], "later")
    assert data.slack_messages[1].topic_id == topic_of_b
    assert len(data.topics) == 2
    assert all(t.title != "A" for t in data.topics)


def test_slack_sync_leaves_gmail_topics_alone():
    # The Gmail side, done by hand: `gmail::add_messages` and
    # `gmail::remove_message` belong to the Gmail source.
    data = VaultData()
    topic_id = new_topic(data, "Budget", "now")
    data.gmail_messages.append(
        GmailMessage(
            "m1", "t1", topic_id, Direction.INBOUND, "a@example.com", "me@example.com", "Budget", "2026-10-22T10:00:00Z"
        )
    )
    domain.apply_sync(data, [meta("D1", "1.0", "Hi")], "now")
    assert len(data.topics) == 2

    data.gmail_messages = [m for m in data.gmail_messages if m.message_id != "m1"]
    prune_topics(data)
    assert len(data.topics) == 1
    assert data.topics[0].title == "Hi"

    domain.clear(data)
    assert data.topics == []


# --- api (slack/api.rs) ---------------------------------------------------


def m(raw: str) -> Match:
    return Match.parse(json.loads(raw))


def test_keeps_only_direct_messages_newest_first_without_duplicates():
    matches = [
        m('{"type":"message","channel":{"id":"C1","name":"general"},"user":"U1","text":"x","ts":"300.0"}'),
        m('{"type":"im","channel":{"id":"D1","name":"U2"},"user":"U2","text":"a","ts":"100.0"}'),
        m(
            '{"type":"message","channel":{"id":"G1","name":"mpdm-a--b-1","is_mpim":true},'
            '"user":"U3","text":"b","ts":"200.0"}'
        ),
        m('{"type":"im","channel":{"id":"D1","name":"U2"},"user":"U2","text":"a","ts":"100.0"}'),
        m('{"type":"im","channel":{"id":"D2","name":"U4","is_im":true},"user":"ME","text":"c","ts":"50.5"}'),
    ]
    picked = api.select_recent(matches, 10)
    assert [(p.channel.id, p.ts) for p in picked] == [("G1", "200.0"), ("D1", "100.0"), ("D2", "50.5")]
    assert len(api.select_recent(picked, 2)) == 2


def test_converts_markup_to_plain_text():
    names = {"U1": "Ana"}
    text = (
        "Hey <@U1>, see <#C9|deploys> and <https://x.example/a?b=1&amp;c=2|the doc> "
        "or <https://y.example>. <!here> &lt;3 <@U7|bo>"
    )
    assert api.plain_text(text, names) == "Hey @Ana, see #deploys and the doc or https://y.example. @here <3 @bo"
    assert api.plain_text("broken <tag", names) == "broken <tag"


def test_finds_mentions():
    assert api.mention_ids("<@U2> and <@U1|ana> and <@U2>") == ["U1", "U2"]
    assert api.mention_ids("no mentions") == []


def test_previews_are_short_and_single_line():
    assert api.preview("  one\n\ntwo  ", 120) == "one two"
    assert api.preview("alpha beta gamma", 12) == "alpha beta…"
    assert api.preview("ñandú ñandú", 7) == "ñandú…"


def test_converts_timestamps():
    assert api.ts_to_rfc3339("1761213600.000200") == "2025-10-23T10:00:00Z"


def test_queries_cover_both_directions():
    assert api.queries("U9") == ["to:me", "from:<@U9>"]


# --- oauth (slack/oauth.rs) -----------------------------------------------


def test_authorization_url_requests_user_scopes_with_pkce():
    url = urlsplit(oauth.authorization_url("123.456", "http://localhost:47615/slack/callback", "chal", "st"))
    q = dict(parse_qsl(url.query))
    assert url.hostname == "slack.com"
    assert q["client_id"] == "123.456"
    assert q["user_scope"] == "search:read,users:read"
    assert "scope" not in q, "no bot scopes on a desktop redirect"
    assert "client_secret" not in q
    assert q["redirect_uri"] == "http://localhost:47615/slack/callback"
    assert q["code_challenge_method"] == "S256"
    assert q["state"] == "st"


def test_reads_user_token_from_initial_exchange():
    r = AccessResponse.parse(
        json.loads(
            """{"ok":true,"app_id":"A1","team":{"id":"T1","name":"Acme"},
                "authed_user":{"id":"U1","scope":"search:read,users:read",
                  "access_token":"xoxp-1","token_type":"user"}}"""
        )
    )
    c, scope = r.credential(1000)
    assert c.access_token == "xoxp-1"
    assert c.refresh_token is None
    assert c.expires_at is None
    assert scope == "search:read,users:read"
    assert not c.needs_refresh(2**63 - 1)


def test_reads_rotating_tokens():
    r = AccessResponse.parse(
        json.loads(
            """{"ok":true,"authed_user":{"id":"U1","scope":"search:read,users:read",
                "access_token":"xoxe.xoxp-1","refresh_token":"xoxe-1-r","expires_in":43200}}"""
        )
    )
    c, _ = r.credential(1000)
    assert c.expires_at == 44200
    assert not c.needs_refresh(1000)
    assert c.needs_refresh(44200 - 30)

    refreshed = AccessResponse.parse(
        json.loads(
            """{"ok":true,"access_token":"xoxe.xoxp-2","refresh_token":"xoxe-1-r2",
                "expires_in":43200,"token_type":"user"}"""
        )
    )
    c, _ = refreshed.credential(2000)
    assert c.access_token == "xoxe.xoxp-2"
    assert c.refresh_token == "xoxe-1-r2"


def test_credential_round_trips_as_json():
    c = Credential("a", "r", 5)
    assert Credential.from_json(c.to_json()) == c


def test_credential_matches_what_rust_stored():
    # `serde_json::to_vec` of the Rust struct.
    assert Credential("a", "r", 5).to_json() == '{"access_token":"a","refresh_token":"r","expires_at":5}'
    assert Credential("a", None, None).to_json() == '{"access_token":"a","refresh_token":null,"expires_at":null}'
    assert Credential.from_json('{"access_token":"a"}') == Credential("a", None, None)
    assert Credential.from_json("not json") is None
    assert Credential.from_json('{"refresh_token":"r"}') is None


def test_redirect_port_comes_from_config():
    assert oauth.SlackClient.from_config(Config()) is None
    assert oauth.SlackClient.from_config(Config(slack_client_id="  ")) is None
    assert oauth.SlackClient.from_config(Config(slack_client_id="1.2")).redirect_port == 47615
    assert (
        oauth.SlackClient.from_config(Config(slack_client_id="1.2", slack_redirect_port=" 5000 ")).redirect_port == 5000
    )
    assert oauth.SlackClient.from_config(Config(slack_client_id="1.2", slack_redirect_port="x")).redirect_port == 47615
    assert (
        oauth.SlackClient.from_config(Config(slack_client_id="1.2", slack_redirect_port="70000")).redirect_port == 47615
    )


# --- service (commands/slack.rs) ------------------------------------------

CLIENT_ID = "123.456"
ACCOUNT = SlackAccount("ME", "me", "T1", "Acme")


class FakeSlack:
    """Answers the Slack endpoints SilentDesk calls, and records the
    requests."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.access: list[dict] = [
            {
                "ok": True,
                "authed_user": {"id": "ME", "scope": "search:read,users:read", "access_token": "xoxp-new"},
            }
        ]
        self.identity = {"ok": True, "user_id": "ME", "user": "me", "team_id": "T1", "team": "Acme"}
        self.search: dict[str, list[dict]] = {
            "to:me": [
                {
                    "type": "im",
                    "channel": {"id": "D1", "name": "U2"},
                    "user": "U2",
                    "text": "Can <@ME> review?",
                    "ts": "1761213600.000200",
                    "permalink": "https://acme.slack.com/archives/D1/p1",
                },
                {
                    "type": "message",
                    "channel": {"id": "C1", "name": "general"},
                    "user": "U2",
                    "text": "channel noise",
                    "ts": "1761213700.0",
                },
            ],
            "from:<@ME>": [
                {
                    "type": "im",
                    "channel": {"id": "D3", "name": "U3"},
                    "user": "ME",
                    "text": "Done",
                    "ts": "1761213500.0",
                }
            ],
        }
        self.search_reply: httpx.Response | None = None
        self.users = {"U2": "Bo", "U3": "Cy", "ME": "Me"}

    def tokens(self, path: str) -> list[str]:
        return [r.headers.get("authorization") for r in self.requests if r.url.path == path]

    def forms(self) -> list[dict[str, str]]:
        return [
            {k: v[0] for k, v in parse_qs(r.content.decode()).items()}
            for r in self.requests
            if r.url.path == "/api/oauth.v2.access"
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "slack.com"
        path = request.url.path
        if path == "/api/oauth.v2.access":
            return httpx.Response(200, json=self.access.pop(0))
        if path == "/api/auth.revoke":
            return httpx.Response(200, json={"ok": True, "revoked": True})
        if path == "/api/auth.test":
            return httpx.Response(200, json=self.identity)
        if path == "/api/search.messages":
            if self.search_reply is not None:
                return self.search_reply
            q = request.url.params
            assert (q["sort"], q["sort_dir"], q["count"]) == ("timestamp", "desc", "30")
            return httpx.Response(200, json={"ok": True, "messages": {"matches": self.search[q["query"]]}})
        if path == "/api/users.info":
            name = self.users.get(request.url.params["user"])
            if name is None:
                return httpx.Response(200, json={"ok": False, "error": "user_not_found"})
            return httpx.Response(200, json={"ok": True, "user": {"name": name.lower(), "real_name": name}})
        raise AssertionError(f"unexpected request {request.url}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def redirect_with(code: str, tasks: list):
    """Plays Slack sending the browser back to the loopback listener."""

    def on_open(url: str) -> None:
        q = dict(parse_qsl(urlsplit(url).query))
        redirect = urlsplit(q["redirect_uri"])

        async def go():
            reader, writer = await asyncio.open_connection("127.0.0.1", redirect.port)
            writer.write(f"GET {redirect.path}?code={code}&state={q['state']} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            await reader.read()
            writer.close()

        tasks.append(asyncio.create_task(go()))

    return on_open


def slack_source(data=None, secrets=None, browser=None, fake=None, configured=True):
    config = Config(slack_client_id=CLIENT_ID, slack_redirect_port=str(free_port())) if configured else Config()
    host = make_host(data=data, secrets=secrets, config=config, browser=browser)
    fake = fake or FakeSlack()
    return SlackSource(host, mock_client(fake)), host, fake


def connected_data() -> VaultData:
    data = VaultData(slack_account=ACCOUNT)
    data.topics.append(Topic("t-old", "Old message", "2026-10-01T00:00:00Z"))
    data.slack_messages.append(
        SlackMessage("D9", "1.0", "t-old", Direction.INBOUND, "Bo", "Bo", "https://x", "2026-10-01T00:00:00Z")
    )
    return data


def stored(credential: Credential) -> dict[str, str]:
    return {SLACK_CREDENTIAL: credential.to_json()}


def test_methods_are_prefixed():
    source, _, _ = slack_source()
    assert set(source.methods()) == {"slack.status", "slack.connect", "slack.sync", "slack.disconnect"}


def test_status_reports_configuration_and_account():
    source, _, _ = slack_source(configured=False)
    assert asyncio.run(source.status()) == status_of(False, False, None)
    with pytest.raises(errors.NotConfigured) as e:
        asyncio.run(source.sync())
    assert "SILENTDESK_SLACK_CLIENT_ID" in e.value.message

    source, _, _ = slack_source(data=VaultData(slack_account=ACCOUNT))
    assert asyncio.run(source.status()) == status_of(True, False, "me · Acme")


def status_of(configured, connected, account):
    return ServiceStatus(configured=configured, connected=connected, account=account)


def test_connect_signs_in_and_stores_the_account():
    tasks: list = []
    browser = FakeBrowser()
    browser.on_open = redirect_with("the-code", tasks)
    source, host, fake = slack_source(browser=browser)

    status = asyncio.run(source.methods()["slack.connect"]({}))

    assert status == status_of(True, True, "me · Acme")
    assert Credential.from_json(host.secrets.get(SLACK_CREDENTIAL)) == Credential("xoxp-new", None, None)
    assert host.store.data().slack_account == ACCOUNT
    (url,) = browser.opened
    q = dict(parse_qsl(urlsplit(url).query))
    assert q["user_scope"] == "search:read,users:read"
    (form,) = fake.forms()
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "the-code"
    assert form["client_id"] == CLIENT_ID
    assert form["redirect_uri"] == q["redirect_uri"]
    assert form["redirect_uri"].startswith("http://localhost:") and form["redirect_uri"].endswith("/slack/callback")
    assert "code_verifier" in form and "client_secret" not in form
    assert fake.tokens("/api/auth.test") == ["Bearer xoxp-new"]


def test_connect_same_account_keeps_topics_and_revokes_old_token():
    tasks: list = []
    browser = FakeBrowser()
    browser.on_open = redirect_with("c", tasks)
    source, host, fake = slack_source(
        data=connected_data(), secrets=stored(Credential("xoxp-old", None, None)), browser=browser
    )

    asyncio.run(source.connect({}))

    assert fake.tokens("/api/auth.revoke") == ["Bearer xoxp-old"]
    assert [t.id for t in host.store.data().topics] == ["t-old"]


def test_connect_different_account_clears_old_data():
    tasks: list = []
    browser = FakeBrowser()
    browser.on_open = redirect_with("c", tasks)
    fake = FakeSlack()
    fake.identity = {"ok": True, "user_id": "U5", "user": "eve", "team_id": "T2", "team": "Other"}
    source, host, _ = slack_source(data=connected_data(), browser=browser, fake=fake)

    status = asyncio.run(source.connect({}))

    assert status.account == "eve · Other"
    data = host.store.data()
    assert data.topics == [] and data.slack_messages == []


def test_connect_requires_both_scopes():
    tasks: list = []
    browser = FakeBrowser()
    browser.on_open = redirect_with("c", tasks)
    fake = FakeSlack()
    fake.access = [{"ok": True, "authed_user": {"scope": "search:read", "access_token": "xoxp-1"}}]
    source, host, _ = slack_source(browser=browser, fake=fake)

    with pytest.raises(errors.Auth) as e:
        asyncio.run(source.connect({}))
    assert e.value.message == "Sign-in failed: Slack access was not fully granted."
    assert host.secrets.get(SLACK_CREDENTIAL) is None


def test_connect_explains_a_wrong_redirect_url():
    tasks: list = []
    browser = FakeBrowser()
    browser.on_open = redirect_with("c", tasks)
    fake = FakeSlack()
    fake.access = [{"ok": False, "error": "bad_redirect_uri"}]
    source, host, _ = slack_source(browser=browser, fake=fake)
    port = oauth.SlackClient.from_config(host.config).redirect_port

    with pytest.raises(errors.Auth) as e:
        asyncio.run(source.connect({}))
    assert f"Add http://localhost:{port}/slack/callback to it." in e.value.message


def test_sync_maps_direct_messages_to_topics():
    source, host, fake = slack_source(data=connected_data(), secrets=stored(Credential("xoxp-1", None, None)))

    views = asyncio.run(source.methods()["slack.sync"]({}))

    assert [v["title"] for v in views] == ["Can @Me review?", "Done"]
    (first,) = views[0]["slackMessages"]
    assert first["channelId"] == "D1"
    assert first["direction"] == "inbound"
    assert (first["author"], first["counterpart"]) == ("Bo", "Bo")
    assert first["date"] == "2025-10-23T10:00:00Z"
    assert first["permalink"] == "https://acme.slack.com/archives/D1/p1"
    (second,) = views[1]["slackMessages"]
    assert (second["direction"], second["author"], second["counterpart"]) == ("outbound", "Me", "Cy")

    data = host.store.data()
    assert [m.channel_id for m in data.slack_messages] == ["D1", "D3"]
    assert all(t.id != "t-old" for t in data.topics)
    assert set(fake.tokens("/api/search.messages")) == {"Bearer xoxp-1"}
    # Each user is looked up once per sync.
    users = [r.url.params["user"] for r in fake.requests if r.url.path == "/api/users.info"]
    assert sorted(users) == sorted(set(users))


def test_sync_refreshes_an_expired_token_and_saves_it():
    fake = FakeSlack()
    fake.access = [{"ok": True, "access_token": "xoxe.xoxp-2", "refresh_token": "xoxe-r2", "expires_in": 43200}]
    expired = Credential("xoxe.xoxp-1", "xoxe-r1", oauth.now() - 10)
    source, host, _ = slack_source(data=connected_data(), secrets=stored(expired), fake=fake)

    asyncio.run(source.sync())

    saved = Credential.from_json(host.secrets.get(SLACK_CREDENTIAL))
    assert saved.access_token == "xoxe.xoxp-2"
    assert saved.refresh_token == "xoxe-r2"
    assert saved.expires_at >= oauth.now() + 43200 - 5
    (form,) = fake.forms()
    assert form == {"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "xoxe-r1"}
    assert set(fake.tokens("/api/search.messages")) == {"Bearer xoxe.xoxp-2"}


def test_refresh_keeps_the_old_refresh_token_when_slack_sends_none():
    fake = FakeSlack()
    fake.access = [{"ok": True, "access_token": "xoxe.xoxp-2", "expires_in": 43200}]
    expired = Credential("xoxe.xoxp-1", "xoxe-r1", oauth.now() - 10)
    source, host, _ = slack_source(data=connected_data(), secrets=stored(expired), fake=fake)

    asyncio.run(source.sync())

    assert Credential.from_json(host.secrets.get(SLACK_CREDENTIAL)).refresh_token == "xoxe-r1"


def test_dead_refresh_token_asks_to_reconnect_and_keeps_topics():
    fake = FakeSlack()
    fake.access = [{"ok": False, "error": "invalid_refresh_token"}]
    expired = Credential("xoxe.xoxp-1", "xoxe-r1", oauth.now() - 10)
    source, host, _ = slack_source(data=connected_data(), secrets=stored(expired), fake=fake)

    with pytest.raises(errors.Reauthorize) as e:
        asyncio.run(source.sync())
    assert e.value.message == "Slack access was revoked or has expired. Connect again."
    assert host.secrets.get(SLACK_CREDENTIAL) is None
    assert [t.id for t in host.store.data().topics] == ["t-old"]
    assert asyncio.run(source.status()) == status_of(True, False, "me · Acme")


def test_revoked_token_asks_to_reconnect_and_keeps_topics():
    fake = FakeSlack()
    fake.search_reply = httpx.Response(200, json={"ok": False, "error": "token_revoked"})
    source, host, _ = slack_source(data=connected_data(), secrets=stored(Credential("xoxp-1", None, None)), fake=fake)

    with pytest.raises(errors.Reauthorize):
        asyncio.run(source.sync())
    assert host.secrets.get(SLACK_CREDENTIAL) is None
    assert [t.id for t in host.store.data().topics] == ["t-old"]
    assert host.store.data().slack_account == ACCOUNT


def test_rate_limit_shows_the_suggested_wait():
    fake = FakeSlack()
    fake.search_reply = httpx.Response(429, headers={"Retry-After": "30"})
    source, host, _ = slack_source(data=connected_data(), secrets=stored(Credential("xoxp-1", None, None)), fake=fake)

    with pytest.raises(errors.Api) as e:
        asyncio.run(source.sync())
    assert e.value.message == "Slack API error (429): rate limited, try again in 30 seconds"
    assert host.secrets.get(SLACK_CREDENTIAL) is not None


def test_other_api_errors_keep_the_credential():
    fake = FakeSlack()
    fake.search_reply = httpx.Response(200, json={"ok": False, "error": "missing_scope"})
    source, host, _ = slack_source(data=connected_data(), secrets=stored(Credential("xoxp-1", None, None)), fake=fake)

    with pytest.raises(errors.Api) as e:
        asyncio.run(source.sync())
    assert e.value.message == "Slack API error (200): missing_scope"
    assert host.secrets.get(SLACK_CREDENTIAL) is not None


def test_sync_without_account_or_token_is_not_connected():
    source, _, _ = slack_source()
    with pytest.raises(errors.NotConnected):
        asyncio.run(source.sync())
    source, _, _ = slack_source(data=connected_data())
    with pytest.raises(errors.NotConnected):
        asyncio.run(source.sync())


def test_unreadable_names_fall_back_to_someone():
    fake = FakeSlack()
    fake.users = {}
    source, _, _ = slack_source(data=connected_data(), secrets=stored(Credential("xoxp-1", None, None)), fake=fake)

    views = asyncio.run(source.sync())

    assert views[0]["title"] == "Can @someone review?"
    assert views[0]["slackMessages"][0]["author"] == "someone"


def test_disconnect_revokes_and_clears_slack_only():
    data = connected_data()
    topic_id = new_topic(data, "Budget", "now")
    data.gmail_messages.append(GmailMessage("m1", "t1", topic_id, Direction.INBOUND, "", "", "Budget", "d"))
    source, host, fake = slack_source(data=data, secrets=stored(Credential("xoxp-1", None, None)))

    status = asyncio.run(source.methods()["slack.disconnect"]({}))

    assert status == status_of(True, False, None)
    assert fake.tokens("/api/auth.revoke") == ["Bearer xoxp-1"]
    assert host.secrets.get(SLACK_CREDENTIAL) is None
    data = host.store.data()
    assert data.slack_account is None and data.slack_messages == []
    assert [t.title for t in data.topics] == ["Budget"]


def test_disconnect_renews_an_expired_token_before_revoking():
    fake = FakeSlack()
    fake.access = [{"ok": True, "access_token": "xoxe.xoxp-2", "expires_in": 43200}]
    expired = Credential("xoxe.xoxp-1", "xoxe-r1", oauth.now() - 10)
    source, host, _ = slack_source(data=connected_data(), secrets=stored(expired), fake=fake)

    asyncio.run(source.disconnect())

    assert fake.tokens("/api/auth.revoke") == ["Bearer xoxe.xoxp-2"]
    assert host.secrets.get(SLACK_CREDENTIAL) is None


def test_disconnect_survives_slack_being_unreachable():
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    host = make_host(
        data=connected_data(),
        secrets=stored(Credential("xoxe.xoxp-1", "r", 0)),
        config=Config(slack_client_id=CLIENT_ID),
    )
    source = SlackSource(host, mock_client(offline))

    asyncio.run(source.disconnect())

    assert host.secrets.get(SLACK_CREDENTIAL) is None
    assert host.store.data().slack_account is None
