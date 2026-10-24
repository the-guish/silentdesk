"""The HTTPS client, the test settings, and the connect, disconnect and sync
commands, against fake connectors where a real one is not built yet."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from silentdesk import api, cli
from silentdesk.adapters.https_client import HttpsClient
from silentdesk.adapters.local_settings import LocalSettings
from silentdesk.contract import AuthError, NetworkError, RemoteError, SyncFailed


def test_test_settings_point_every_service_at_the_fake_server():
    settings = LocalSettings.from_environment(
        {
            "HOME": "/home/ana",
            "SILENTDESK_TEST_BASE_URL": "http://127.0.0.1:9/",
            "SILENTDESK_TEST_NOW": "2026-10-24T12:00:00Z",
        }
    )
    assert settings.base_url("github", "https://api.github.com") == "http://127.0.0.1:9/github"
    assert settings.now == "2026-10-24T12:00:00Z"
    assert LocalSettings.from_environment({"HOME": "/h"}).base_url("github", "https://api.github.com") == (
        "https://api.github.com"
    )


def echo(request: httpx.Request) -> httpx.Response:
    return httpx.Response(201, json={"url": str(request.url), "body": request.content.decode()})


def test_https_client_sends_json_or_form_bodies():
    http = HttpsClient(transport=httpx.MockTransport(echo))

    async def calls():
        a = await http.request("POST", "https://example.com/a", params={"q": "1"}, json={"x": 1})
        b = await http.request("POST", "https://example.com/b", form={"code": "c d"})
        await http.close()
        return a, b

    a, b = asyncio.run(calls())
    assert a.status == 201
    assert json.loads(a.body) == {"url": "https://example.com/a?q=1", "body": '{"x":1}'}
    assert json.loads(b.body)["body"] == "code=c+d"


@pytest.mark.parametrize(
    ("url", "allow_loopback_http", "allowed"),
    [
        ("http://example.com/", True, False),
        ("http://127.0.0.1:8000/", False, False),
        ("http://127.0.0.1:8000/", True, True),
        ("http://localhost/", True, True),
    ],
)
def test_https_client_refuses_plain_http_except_to_loopback_in_tests(url, allow_loopback_http, allowed):
    http = HttpsClient(allow_loopback_http, transport=httpx.MockTransport(echo))

    async def call():
        try:
            return await http.request("GET", url)
        finally:
            await http.close()

    if allowed:
        assert asyncio.run(call()).status == 201
    else:
        with pytest.raises(NetworkError, match="Only https"):
            asyncio.run(call())


def test_https_client_checks_where_redirects_lead():
    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://example.com/plain"})

    http = HttpsClient(transport=httpx.MockTransport(redirect))
    with pytest.raises(NetworkError, match="Only https"):
        asyncio.run(http.request("GET", "https://example.com/"))


@pytest.fixture
def settings(tmp_path, monkeypatch) -> LocalSettings:
    settings = LocalSettings(tmp_path / "data", google_client_id="client", test_keyring=tmp_path / "keyring.json")
    monkeypatch.setattr(api.LocalSettings, "from_environment", classmethod(lambda cls: settings))
    return settings


def run(*argv: str, stdin: str = "") -> tuple[int, dict]:
    return cli.run(list(argv), lambda: stdin)


def test_connect_and_disconnect_need_exactly_one_known_service(settings):
    assert run("connect")[1]["error"]["kind"] == "usage"
    assert run("disconnect", "gmail", "tasks")[1]["error"]["kind"] == "usage"
    code, document = run("connect", "zulip")
    assert (code, document["error"]["kind"]) == (cli.EXIT_USAGE, "usage")
    assert "Services: github, gmail, jira, tasks." in document["error"]["message"]


@pytest.mark.parametrize("stdin", ["not json", "[1]", '{"token": 1}'])
def test_connect_fields_must_be_a_json_object_of_strings(settings, stdin):
    code, document = run("connect", "gmail", stdin=stdin)
    assert (code, document["error"]["kind"]) == (cli.EXIT_USAGE, "usage")


def test_disconnect_forgets_the_refresh_token(settings):
    settings.test_keyring.write_text(json.dumps({"gmail-refresh-token": "t"}))
    code, document = run("disconnect", "gmail")
    assert (code, document) == (
        cli.EXIT_OK,
        {"service": "gmail", "configured": True, "connected": False, "account": None},
    )
    assert "gmail-refresh-token" not in json.loads(settings.test_keyring.read_text())


def test_syncing_a_service_that_is_not_connected_is_an_auth_error(settings):
    code, document = run("sync", "gmail")
    assert (code, document) == (
        cli.EXIT_FAILED,
        {"error": {"kind": "auth", "message": "Gmail is not connected."}},
    )


def test_a_round_with_nothing_connected_changes_nothing(settings):
    assert run("sync") == (cli.EXIT_OK, {"lastSynced": None})


def test_a_failed_round_lists_each_failed_service(settings, monkeypatch):
    async def failing_sync(self, service=None):
        raise SyncFailed([("github", AuthError("github", "Rejected.")), ("jira", RemoteError("jira", "Down.", 503))])

    monkeypatch.setattr(type(api.desk()), "sync", failing_sync)
    code, document = run("sync")
    assert code == cli.EXIT_FAILED
    assert document == {
        "error": {
            "kind": "sync",
            "message": "2 services failed to sync.",
            "failures": [
                {"service": "github", "kind": "auth", "message": "Rejected."},
                {"service": "jira", "kind": "remote", "message": "Down."},
            ],
        }
    }
