import asyncio

from silentdesk.adapters import oauth
from silentdesk.core import errors
from silentdesk.core.model import (
    Direction,
    GmailMessage,
    JiraIssue,
    Topic,
    VaultData,
    from_json,
    to_json,
)
from silentdesk.core.topics import prune_topics, topic_views


def gmail(topic_id: str, date: str, id: str = "m") -> GmailMessage:
    return GmailMessage(id, "t", topic_id, Direction.INBOUND, "", "", "s", date)


def jira(topic_id: str, date: str) -> JiraIssue:
    return JiraIssue("1", "K-1", topic_id, Direction.INBOUND, "", "", "", "", "", date)


def test_json_round_trip_uses_rust_field_names():
    data = VaultData(topics=[Topic("a", "A", "2026-01-01T00:00:00Z")], gmail_messages=[gmail("a", "d")])
    encoded = to_json(data)
    assert encoded["gmailMessages"][0]["from"] == ""
    assert encoded["gmailMessages"][0]["direction"] == "inbound"
    assert encoded["topics"][0]["createdAt"] == "2026-01-01T00:00:00Z"
    assert encoded["gmailAccount"] is None
    assert from_json(VaultData, encoded) == data


def test_missing_keys_take_defaults():
    assert from_json(VaultData, {}) == VaultData()


def test_prune_keeps_topics_with_items():
    data = VaultData(topics=[Topic("a", "A", ""), Topic("b", "B", "")], jira_issues=[jira("b", "d")])
    prune_topics(data)
    assert [t.id for t in data.topics] == ["b"]


def test_topic_views_sort_by_latest_item():
    data = VaultData(
        topics=[Topic("a", "A", "2026-01-01"), Topic("b", "B", "2026-01-02"), Topic("c", "C", "2026-01-05")],
        gmail_messages=[gmail("a", "2026-01-03", "1"), gmail("a", "2026-01-04", "2")],
        jira_issues=[jira("b", "2026-01-06")],
    )
    views = topic_views(data)
    assert [v["id"] for v in views] == ["b", "c", "a"]
    assert [m["messageId"] for m in views[2]["emails"]] == ["2", "1"]
    assert views[1]["emails"] == [] and views[1]["pullRequests"] == []


def test_pkce_challenge_is_s256_of_verifier():
    import base64
    import hashlib

    p = oauth.pkce()
    assert len(p.verifier) == 43
    digest = hashlib.sha256(p.verifier.encode()).digest()
    assert p.challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_rfc7636_example():
    import hashlib

    digest = hashlib.sha256(b"dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk").digest()
    assert oauth.b64url(digest) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_parses_callback():
    assert oauth.parse_callback("GET /?state=s1&code=4%2Fabc&scope=x HTTP/1.1", "/", "s1") == "4/abc"
    assert isinstance(oauth.parse_callback("GET /?state=other&code=abc HTTP/1.1", "/", "s1"), errors.Auth)
    assert isinstance(oauth.parse_callback("GET /?state=s1&error=access_denied HTTP/1.1", "/", "s1"), errors.Auth)
    assert oauth.parse_callback("GET /favicon.ico HTTP/1.1", "/", "s1") is None
    assert oauth.parse_callback("GET / HTTP/1.1", "/", "s1") is None
    assert oauth.parse_callback("POST /?code=a&state=s1 HTTP/1.1", "/", "s1") is None
    assert oauth.parse_callback("", "/", "s1") is None


def test_parses_callback_on_a_path():
    assert oauth.parse_callback("GET /slack/callback?code=c&state=s1 HTTP/1.1", "/slack/callback", "s1") == "c"
    assert oauth.parse_callback("GET /?code=c&state=s1 HTTP/1.1", "/slack/callback", "s1") is None


async def _get(port: int, path: str) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    await writer.drain()
    response = await reader.read()
    writer.close()
    return response


def test_loopback_receives_code_after_unrelated_request():
    async def run():
        loopback = await oauth.Loopback.any_port()
        port = int(loopback.redirect_uri.rsplit(":", 1)[1])
        waiting = asyncio.create_task(loopback.wait_for_code("s1"))
        await asyncio.sleep(0)
        assert (await _get(port, "/favicon.ico")).startswith(b"HTTP/1.1 404")
        assert (await _get(port, "/?code=the-code&state=s1")).startswith(b"HTTP/1.1 200")
        return await waiting

    assert asyncio.run(run()) == "the-code"


def test_fixed_port_in_use_is_explained():
    async def run():
        taken = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = taken.sockets[0].getsockname()[1]
        try:
            await oauth.Loopback.fixed(port, "/cb", "SOME_PORT_VAR")
        except errors.Auth as e:
            return e.message
        finally:
            taken.close()

    assert "SOME_PORT_VAR" in asyncio.run(run())
