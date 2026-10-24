import asyncio
import json

import httpx
import pytest

from silentdesk.core import errors
from silentdesk.core.model import (
    Direction,
    GitHubAccount,
    GitHubEndpoint,
    PullRequest,
    PullRequestReason,
    Topic,
    VaultData,
)
from silentdesk.core.secret_names import GITHUB_TOKEN
from silentdesk.sources.github import GitHubSource, api, domain
from silentdesk.sources.github.api import PullMeta

from .fakes import make_host, mock_client

Reason = PullRequestReason

# --- Ported from src-tauri/src/github/mod.rs ------------------------------


def meta(id: int, title: str) -> PullMeta:
    return PullMeta(
        pr_id=id,
        repo="acme/web",
        number=id,
        title=title,
        reason=Reason.REVIEW_REQUESTED,
        direction=Direction.INBOUND,
        draft=False,
        author="ana",
        url=f"https://github.com/acme/web/pull/{id}",
        date="2026-10-23T10:00:00Z",
    )


def test_each_pull_request_gets_its_own_topic():
    data = VaultData()
    domain.apply_sync(data, [meta(1, "Add retries"), meta(2, "")], "now")
    assert [t.title for t in data.topics] == ["Add retries", "acme/web#2"]


def test_resync_keeps_topics_and_drops_closed_pull_requests():
    data = VaultData()
    domain.apply_sync(data, [meta(1, "A"), meta(2, "B")], "now")
    topic_of_b = data.pull_requests[1].topic_id
    domain.apply_sync(data, [meta(2, "B"), meta(3, "C")], "later")
    assert data.pull_requests[0].topic_id == topic_of_b
    assert len(data.topics) == 2
    assert all(t.title != "A" for t in data.topics)

    domain.clear(data)
    assert data.topics == []


# --- Ported from src-tauri/src/github/api.rs ------------------------------


def item(text: str) -> api.RawItem:
    return api.read_item(json.loads(text))


def test_endpoints_for_github_com_and_enterprise():
    dotcom = api.endpoint_for_server(None)
    assert dotcom.api_base == "https://api.github.com"
    assert api.endpoint_for_server("  ") == dotcom
    assert api.endpoint_for_server("https://github.com/") == dotcom

    ghes = api.endpoint_for_server("github.acme.com/")
    assert ghes.api_base == "https://github.acme.com/api/v3"
    assert ghes.web_base == "https://github.acme.com"
    assert api.host(ghes) == "github.acme.com"

    with pytest.raises(errors.Auth):
        api.endpoint_for_server("http://github.acme.com")


def test_every_query_names_pull_requests():
    assert all(q.startswith("is:pr ") for q, _ in api.QUERIES)


def test_parses_search_items():
    m = api.to_meta(
        item(
            """{"id":11,"number":42,"title":" Add retries ","draft":true,
                "html_url":"https://github.com/acme/web/pull/42",
                "repository_url":"https://api.github.com/repos/acme/web",
                "user":{"login":"ana"},"updated_at":"2026-10-23T10:00:00Z",
                "pull_request":{"url":"x"}}"""
        ),
        Reason.REVIEW_REQUESTED,
    )
    assert m.repo == "acme/web"
    assert m.title == "Add retries"
    assert m.direction == Direction.INBOUND
    assert m.draft
    assert m.author == "ana"


def test_merges_duplicates_keeping_the_strongest_reason():
    def raw(id: int, date: str) -> api.RawItem:
        return item(
            f"""{{"id":{id},"number":{id},"title":"t","html_url":"u",
                "repository_url":"https://ghe.acme.com/api/v3/repos/acme/api",
                "updated_at":"{date}"}}"""
        )

    pulls = api.merge(
        [
            (raw(1, "2026-10-20T00:00:00Z"), Reason.REVIEW_REQUESTED),
            (raw(2, "2026-10-22T00:00:00Z"), Reason.ASSIGNED),
            (raw(1, "2026-10-20T00:00:00Z"), Reason.ASSIGNED),
            (raw(3, "2026-10-21T00:00:00Z"), Reason.AUTHORED),
        ]
    )
    assert [(p.pr_id, p.reason) for p in pulls] == [
        (2, Reason.ASSIGNED),
        (3, Reason.AUTHORED),
        (1, Reason.REVIEW_REQUESTED),
    ]
    assert pulls[1].direction == Direction.OUTBOUND
    assert pulls[0].repo == "acme/api"


# --- Beyond the Rust tests ------------------------------------------------


def test_enterprise_server_addresses():
    assert api.endpoint_for_server("GitHub.Acme.com:8443/some/path") == GitHubEndpoint(
        "https://github.acme.com:8443/api/v3", "https://github.acme.com:8443"
    )
    assert api.endpoint_for_server("https://github.acme.com:443") == GitHubEndpoint(
        "https://github.acme.com/api/v3", "https://github.acme.com"
    )
    assert api.endpoint_for_server("api.github.com") == api.endpoint_for_server(None)
    for bad in ["https://", "github acme.com", "github.acme.com:x"]:
        with pytest.raises(errors.Auth, match="the GitHub server address is not valid."):
            api.endpoint_for_server(bad)
    with pytest.raises(errors.Auth, match="the GitHub server must use https://."):
        api.endpoint_for_server("ws://github.acme.com")


def test_equal_dates_sort_by_id():
    def raw(id: int) -> api.RawItem:
        return item(f'{{"id":{id},"number":1,"html_url":"u","repository_url":"r","updated_at":"d"}}')

    pulls = api.merge([(raw(3), Reason.ASSIGNED), (raw(1), Reason.ASSIGNED), (raw(2), Reason.ASSIGNED)])
    assert [p.pr_id for p in pulls] == [1, 2, 3]
    assert pulls[0].repo == "r" and pulls[0].author == "" and pulls[0].title == ""


# --- The source -----------------------------------------------------------

DOTCOM = GitHubEndpoint("https://api.github.com", "https://github.com")


def raw_item(id: int, title: str, date: str = "2026-10-23T10:00:00Z") -> dict:
    return {
        "id": id,
        "number": id,
        "title": title,
        "html_url": f"https://github.com/acme/web/pull/{id}",
        "repository_url": "https://api.github.com/repos/acme/web",
        "user": {"login": "ana"},
        "draft": False,
        "updated_at": date,
    }


class FakeGitHub:
    """Answers `/user` and the three searches, recording each request."""

    def __init__(self, user=None, by_qualifier: dict[str, list[dict]] | None = None, status: int = 200):
        self.user = user if user is not None else {"login": "luis", "name": "Luis Castro"}
        self.by_qualifier = by_qualifier or {}
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"message": "Bad credentials"})
        path = request.url.path.removeprefix("/api/v3")
        if path == "/user":
            return httpx.Response(200, json=self.user)
        if path == "/search/issues":
            qualifier = request.url.params["q"].rsplit(" ", 1)[1]
            return httpx.Response(200, json={"items": self.by_qualifier.get(qualifier, [])})
        return httpx.Response(404, json={"message": "Not Found"})


def connected(data: VaultData | None = None):
    data = data or VaultData(github_account=GitHubAccount(DOTCOM, "luis", "Luis Castro"))
    return make_host(data, {GITHUB_TOKEN: "ghp_x"})


def test_connect_stores_raw_token_and_account():
    host = make_host()
    fake = FakeGitHub(user={"login": "luis", "name": "  "})
    s = GitHubSource(host, mock_client(fake))
    status = asyncio.run(s.methods()["github.connect"]({"server": None, "token": " ghp_x "}))
    assert (status.configured, status.connected, status.account) == (True, True, "luis · github.com")
    request = fake.requests[0]
    assert str(request.url) == "https://api.github.com/user"
    assert request.headers["authorization"] == "Bearer ghp_x"
    assert request.headers["accept"] == "application/vnd.github+json"
    assert request.headers["x-github-api-version"] == "2022-11-28"
    assert host.secrets.values == {GITHUB_TOKEN: "ghp_x"}
    # A blank name falls back to the login.
    assert host.store.data().github_account == GitHubAccount(DOTCOM, "luis", "luis")


def test_connect_enterprise_server():
    host = make_host()
    fake = FakeGitHub()
    s = GitHubSource(host, mock_client(fake))
    status = asyncio.run(s.connect({"server": "github.acme.com", "token": "t"}))
    assert str(fake.requests[0].url) == "https://github.acme.com/api/v3/user"
    assert status.account == "luis · github.acme.com"


def test_connect_failures_store_nothing():
    for server, fake, message in [
        (None, FakeGitHub(status=401), "Sign-in failed: GitHub rejected the token. Check it, and its expiry."),
        (
            "git.acme.com",
            lambda r: httpx.Response(404),
            "Sign-in failed: no GitHub API was found at git.acme.com. Check the server address.",
        ),
        (None, FakeGitHub(status=403), "GitHub API error (403): Bad credentials"),
        (None, lambda r: httpx.Response(500, text="oops"), "GitHub API error (500): Internal Server Error"),
        (None, FakeGitHub(user={"name": "no login"}), "Network error: error decoding response body"),
    ]:
        host = make_host()
        s = GitHubSource(host, mock_client(fake))
        with pytest.raises(errors.AppError) as e:
            asyncio.run(s.connect({"server": server, "token": "t"}))
        assert str(e.value) == message
        assert host.secrets.values == {} and host.store.writes == 0


def test_connect_checks_input_before_any_request():
    for params, message in [
        ({"server": "http://github.acme.com", "token": "t"}, "Sign-in failed: the GitHub server must use https://."),
        ({"token": " "}, "Sign-in failed: enter a personal access token."),
    ]:
        fake = FakeGitHub()
        s = GitHubSource(make_host(), mock_client(fake))
        with pytest.raises(errors.Auth) as e:
            asyncio.run(s.connect(params))
        assert str(e.value) == message
        assert fake.requests == []


def test_connect_as_another_account_or_server_clears_old_data():
    old_pr = PullRequest(9, "acme/old", 9, "t1", Reason.AUTHORED, Direction.OUTBOUND, False, "luis", "u", "d")
    for account, kept in [
        (GitHubAccount(DOTCOM, "luis", "Luis"), True),
        (GitHubAccount(DOTCOM, "someone", "Someone"), False),
        (GitHubAccount(api.endpoint_for_server("github.acme.com"), "luis", "Luis"), False),
    ]:
        host = make_host(VaultData(topics=[Topic("t1", "Old", "c")], github_account=account, pull_requests=[old_pr]))
        s = GitHubSource(host, mock_client(FakeGitHub()))
        asyncio.run(s.connect({"server": None, "token": "t"}))
        data = host.store.data()
        assert (data.pull_requests == [old_pr]) is kept
        assert ([t.id for t in data.topics] == ["t1"]) is kept
        assert data.github_account == GitHubAccount(DOTCOM, "luis", "Luis Castro")


def test_sync_runs_three_searches_and_merges():
    host = connected()
    fake = FakeGitHub(
        by_qualifier={
            "review-requested:@me": [raw_item(1, "Review me", "2026-10-20T00:00:00Z")],
            "assignee:@me": [raw_item(1, "Review me", "2026-10-20T00:00:00Z"), raw_item(2, "", "2026-10-22T00:00:00Z")],
            "author:@me": [raw_item(3, " Mine ", "2026-10-21T00:00:00Z")],
        }
    )
    s = GitHubSource(host, mock_client(fake))
    views = asyncio.run(s.methods()["github.sync"]({}))
    assert [dict(r.url.params) for r in fake.requests] == [
        {"q": q, "sort": "updated", "order": "desc", "per_page": "50"} for q, _ in api.QUERIES
    ]
    assert all(r.headers["authorization"] == "Bearer ghp_x" for r in fake.requests)
    assert [v["title"] for v in views] == ["acme/web#2", "Mine", "Review me"]
    data = host.store.data()
    assert [(p.pr_id, p.reason, p.direction) for p in data.pull_requests] == [
        (2, Reason.ASSIGNED, Direction.INBOUND),
        (3, Reason.AUTHORED, Direction.OUTBOUND),
        (1, Reason.REVIEW_REQUESTED, Direction.INBOUND),
    ]
    assert views[0]["pullRequests"][0]["reason"] == "assigned"


def test_resync_keeps_topics():
    host = connected()
    fake = FakeGitHub(by_qualifier={"author:@me": [raw_item(1, "A"), raw_item(2, "B")]})
    s = GitHubSource(host, mock_client(fake))
    asyncio.run(s.sync())
    topic_of_b = host.store.data().pull_requests[1].topic_id
    fake.by_qualifier = {"author:@me": [raw_item(2, "B renamed")]}
    asyncio.run(s.sync())
    data = host.store.data()
    assert [t.id for t in data.topics] == [topic_of_b]
    assert data.topics[0].title == "B"


def test_sync_when_not_connected():
    for host in [make_host(), make_host(VaultData(github_account=GitHubAccount(DOTCOM, "luis", "Luis")))]:
        s = GitHubSource(host, mock_client(FakeGitHub()))
        with pytest.raises(errors.NotConnected, match="GitHub is not connected."):
            asyncio.run(s.sync())


def test_sync_with_revoked_token_forgets_it_and_keeps_topics():
    host = connected()
    fake = FakeGitHub(by_qualifier={"author:@me": [raw_item(1, "A")]})
    s = GitHubSource(host, mock_client(fake))
    asyncio.run(s.sync())
    fake.status = 401
    with pytest.raises(errors.Reauthorize) as e:
        asyncio.run(s.sync())
    assert str(e.value) == "GitHub access was revoked or has expired. Connect again."
    assert host.secrets.values == {}
    assert [t.title for t in host.store.data().topics] == ["A"]
    assert asyncio.run(s.status()).connected is False


def test_sync_errors_keep_the_token():
    def unreachable(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    for handler, message in [
        (unreachable, "Network error: timed out"),
        (
            lambda r: httpx.Response(422, json={"message": "Validation Failed"}),
            "GitHub API error (422): Validation Failed",
        ),
        (lambda r: httpx.Response(422, text=""), "GitHub API error (422): Unprocessable Entity"),
        (lambda r: httpx.Response(200, json={"items": [{"id": -1}]}), "Network error: error decoding response body"),
    ]:
        host = connected()
        s = GitHubSource(host, mock_client(handler))
        with pytest.raises(errors.AppError) as e:
            asyncio.run(s.sync())
        assert str(e.value) == message
        assert host.secrets.values == {GITHUB_TOKEN: "ghp_x"}


def test_disconnect_forgets_everything():
    host = connected()
    s = GitHubSource(host, mock_client(FakeGitHub(by_qualifier={"author:@me": [raw_item(1, "A")]})))
    asyncio.run(s.sync())
    status = asyncio.run(s.methods()["github.disconnect"]({}))
    assert (status.connected, status.account) == (False, None)
    assert host.secrets.values == {}
    data = host.store.data()
    assert data.github_account is None and data.pull_requests == [] and data.topics == []


def test_methods_are_named_for_the_ui():
    s = GitHubSource(make_host(), mock_client(FakeGitHub()))
    assert sorted(s.methods()) == ["github.connect", "github.disconnect", "github.status", "github.sync"]
