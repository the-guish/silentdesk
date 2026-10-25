"""The shared browser sign-in: PKCE, the loopback redirect and the token exchange."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import socket
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from silentdesk.adapters.https_client import HttpsClient
from silentdesk.adapters.loopback_oauth import LoopbackOAuth
from silentdesk.contract import AuthError, Browser, OAuthClient

CLIENT = OAuthClient("tasks", "https://accounts.example/auth", "https://oauth.example/token", "client-1", "secret")


class RedirectingBrowser(Browser):
    """Goes straight back to the loopback redirect, as Google would after
    sign-in, with the given parameters; `state` defaults to the one sent."""

    def __init__(self, **params: str) -> None:
        self.params = params
        self.opened: list[str] = []

    async def open(self, url: str) -> None:
        self.opened.append(url)
        query = {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}
        params = {"state": query["state"], **self.params}
        # Straight to the loopback listener, never through a proxy.
        async with httpx.AsyncClient(trust_env=False) as client:
            await client.get(query["redirect_uri"], params=params)


def token_endpoint(seen: list[dict], body: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(status, json=body)

    return HttpsClient(transport=httpx.MockTransport(handler))


TOKENS = {"access_token": "a", "refresh_token": "r", "scope": "s1 s2"}


def test_sign_in_sends_a_pkce_challenge_and_exchanges_the_code_with_its_verifier():
    seen: list[dict] = []
    browser = RedirectingBrowser(code="code-1")
    oauth = LoopbackOAuth(token_endpoint(seen, TOKENS), browser)

    tokens = asyncio.run(oauth.sign_in(CLIENT, ["s1", "s2"]))

    assert (tokens.access_token, tokens.refresh_token, tokens.scopes) == ("a", "r", ("s1", "s2"))
    sent = {k: v[0] for k, v in parse_qs(urlsplit(browser.opened[0]).query).items()}
    assert sent["scope"] == "s1 s2" and sent["code_challenge_method"] == "S256"
    assert sent["redirect_uri"].startswith("http://127.0.0.1:")
    [form] = seen
    assert form["code"] == "code-1" and form["client_secret"] == "secret"
    assert form["redirect_uri"] == sent["redirect_uri"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert challenge == sent["code_challenge"]


@pytest.mark.parametrize(
    ("params", "match"),
    [({"error": "access_denied"}, "Access was denied"), ({"code": "c", "state": "forged"}, "did not match")],
)
def test_a_declined_or_forged_redirect_is_refused(params, match):
    oauth = LoopbackOAuth(token_endpoint([], TOKENS), RedirectingBrowser(**params))
    with pytest.raises(AuthError, match=match):
        asyncio.run(oauth.sign_in(CLIENT, ["s1"]))


def test_a_sign_in_that_never_comes_back_times_out():
    class IdleBrowser(Browser):
        async def open(self, url: str) -> None:
            pass

    oauth = LoopbackOAuth(token_endpoint([], TOKENS), IdleBrowser(), timeout=0.05)
    with pytest.raises(AuthError, match="did not finish in time"):
        asyncio.run(oauth.sign_in(CLIENT, ["s1"]))


@pytest.mark.parametrize(
    ("error", "match"),
    [("invalid_grant", "expired or was revoked"), ("invalid_client", "client was rejected"), ("other", "other")],
)
def test_token_errors_are_auth_errors(error, match):
    oauth = LoopbackOAuth(token_endpoint([], {"error": error}, status=400), RedirectingBrowser())
    with pytest.raises(AuthError, match=match):
        asyncio.run(oauth.refresh(CLIENT, "r"))


def test_revoking_is_best_effort():
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    oauth = LoopbackOAuth(HttpsClient(transport=httpx.MockTransport(unreachable)), RedirectingBrowser())
    asyncio.run(oauth.revoke("https://oauth.example/revoke", "r"))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_fixed_port_redirect_uses_localhost_and_the_registered_path():
    port = free_port()
    client = OAuthClient(
        "slack", "https://slack.example/authorize", "https://slack.example/token", "c", port=port, path="/cb"
    )
    browser = RedirectingBrowser(code="c")

    tokens = asyncio.run(LoopbackOAuth(token_endpoint([], {**TOKENS, "extra": 1}), browser).sign_in(client, ["s"]))

    sent = parse_qs(urlsplit(browser.opened[0]).query)
    assert sent["redirect_uri"] == [f"http://localhost:{port}/cb"]
    assert tokens.raw["extra"] == 1
