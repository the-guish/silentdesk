"""The GitHub connector: its rules, its use cases and its HTTP adapter."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.https_client import HttpsClient
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.github.adapters.github_http import GitHubHttpApi
from silentdesk.apps.github.adapters.keyring_credentials import KeyringCredentials
from silentdesk.apps.github.adapters.sqlcipher_state_store import SqlcipherStateStore
from silentdesk.apps.github.application.github import GitHub
from silentdesk.apps.github.core import github
from silentdesk.apps.github.domain.github import PullRequest, Reason
from silentdesk.apps.github.ports.github_api import Found, GitHubApi, Me
from silentdesk.contract import (
    AuthError,
    Direction,
    NetworkError,
    RemoteError,
    StatusCategory,
    TopicStatus,
    Unsupported,
)


def pull(pr_id: int, reason: Reason = Reason.REVIEW_REQUESTED, updated: str = "2026-10-23T10:00:00Z", title="Fix"):
    return PullRequest(
        pr_id, "acme/web", pr_id, title, reason, "ana", False, f"https://github.com/acme/web/pull/{pr_id}", updated
    )


def test_endpoints_for_github_com_and_enterprise_server():
    assert github.endpoint_for_server(None) == github.GITHUB_COM
    assert github.endpoint_for_server("  ") == github.GITHUB_COM
    assert github.endpoint_for_server("https://github.com/") == github.GITHUB_COM

    ghes = github.endpoint_for_server("github.acme.com/")
    assert (ghes.api_base, ghes.web_base) == ("https://github.acme.com/api/v3", "https://github.acme.com")
    assert github.endpoint_for_server("github.acme.com:8443").api_base == "https://github.acme.com:8443/api/v3"

    with pytest.raises(AuthError, match="https"):
        github.endpoint_for_server("http://github.acme.com")
    with pytest.raises(AuthError, match="not valid"):
        github.endpoint_for_server("https://")


def test_merge_keeps_the_strongest_reason_and_sorts_newest_first():
    merged = github.merge(
        [
            pull(1, Reason.REVIEW_REQUESTED, "2026-10-01T00:00:00Z"),
            pull(2, Reason.ASSIGNED, "2026-10-05T00:00:00Z"),
            pull(1, Reason.AUTHORED, "2026-10-01T00:00:00Z"),
            pull(3, Reason.AUTHORED, "2026-10-05T00:00:00Z"),
        ]
    )
    assert [(p.pr_id, p.reason) for p in merged] == [
        (2, Reason.ASSIGNED),
        (3, Reason.AUTHORED),
        (1, Reason.REVIEW_REQUESTED),
    ]


def test_a_pull_request_is_a_topic_with_one_item():
    topic = github.topic(pull(7, Reason.AUTHORED, title="  "))
    assert (topic.key, topic.title) == ("7", "acme/web#7")
    [item] = topic.items
    assert (item.key, item.direction, item.author) == ("7", Direction.OUTBOUND, "ana")
    assert topic.status == TopicStatus("In Review", StatusCategory.IN_PROGRESS)


def state(**fields) -> PullRequest:
    return replace(pull(1), **fields)


@pytest.mark.parametrize(
    ("pull_request", "name"),
    [
        (state(merged=True, closed=True, checks="FAILURE"), "Merged"),
        (state(closed=True, checks="FAILURE"), "Closed"),
        (state(checks="FAILURE", review="APPROVED"), "CI Failed"),
        (state(checks="ERROR", draft=True), "CI Failed"),
        (state(checks="SUCCESS", review="APPROVED"), "Approved"),
        (state(checks="PENDING", review="APPROVED"), "Approved"),
        (state(review="CHANGES_REQUESTED"), "Changes Requested"),
        (state(review="REVIEW_REQUIRED"), "In Review"),
        (state(), "In Review"),
        (state(draft=True, checks="PENDING"), "Draft"),
        (state(draft=True, review="REVIEW_REQUIRED"), "Draft"),
    ],
)
def test_the_first_status_that_applies_wins(pull_request, name):
    assert github.status(pull_request).name == name


@pytest.mark.parametrize(
    ("name", "category"),
    [("Merged", StatusCategory.DONE), ("Closed", StatusCategory.DONE), ("Draft", StatusCategory.NEW)]
    + [(n, StatusCategory.IN_PROGRESS) for n in ("CI Failed", "Approved", "Changes Requested", "In Review")],
)
def test_each_status_has_its_category(name, category):
    assert github.STATUS_CATEGORIES[name] == category


@pytest.mark.parametrize(
    ("api_base", "url"),
    [
        ("https://api.github.com", "https://api.github.com/graphql"),
        ("https://github.acme.com/api/v3", "https://github.acme.com/api/graphql"),
        ("https://github.acme.com:8443/api/v3", "https://github.acme.com:8443/api/graphql"),
        ("http://127.0.0.1:5000/github", "http://127.0.0.1:5000/github/graphql"),
    ],
)
def test_graphql_lives_next_to_the_rest_api(api_base, url):
    assert github.graphql_url(api_base) == url


ANA = Me("ana", "Ana Ruiz")


class FakeApi(GitHubApi):
    def __init__(self, me: Me | Exception = ANA, found: list | Exception = (), complete: bool = True):
        self._me, self.found, self.complete, self.calls = me, found, complete, []

    async def me(self, api_base, token):
        self.calls.append(("me", api_base, token))
        if isinstance(self._me, Exception):
            raise self._me
        return self._me

    async def open_pull_requests(self, api_base, token, queries):
        self.calls.append(("pulls", api_base, list(queries)))
        if isinstance(self.found, Exception):
            raise self.found
        return Found(list(self.found), self.complete)


@pytest.fixture
def keyring(tmp_path) -> FileKeyring:
    return FileKeyring(tmp_path / "keyring.json")


def connector(tmp_path, keyring, api: FakeApi) -> GitHub:
    database = SqlcipherDatabase(tmp_path / "silentdesk.db", keyring)
    return GitHub(api, KeyringCredentials(keyring), SqlcipherStateStore(database), lambda e: e.api_base)


def test_connect_checks_the_token_then_keeps_it(tmp_path, keyring):
    api = FakeApi()
    status = asyncio.run(connector(tmp_path, keyring, api).connect({"token": " ghp_x ", "server": "github.acme.com"}))
    assert (status.connected, status.account) == (True, "ana · github.acme.com")
    assert keyring.get("github-token") == "ghp_x"
    assert api.calls == [("me", "https://github.acme.com/api/v3", "ghp_x")]


def test_a_rejected_token_stores_nothing(tmp_path, keyring):
    github_app = connector(tmp_path, keyring, FakeApi(me=AuthError("github", "Rejected.")))
    with pytest.raises(AuthError):
        asyncio.run(github_app.connect({"token": "bad"}))
    assert keyring.get("github-token") is None
    assert asyncio.run(github_app.status()).connected is False


def test_connect_needs_a_token(tmp_path, keyring):
    with pytest.raises(AuthError, match="personal access token"):
        asyncio.run(connector(tmp_path, keyring, FakeApi()).connect({}))


def test_sync_sends_the_three_queries_at_once_and_returns_every_pull_request(tmp_path, keyring):
    api = FakeApi(found=[pull(1), pull(2, Reason.AUTHORED, "2026-10-24T00:00:00Z")])
    app = connector(tmp_path, keyring, api)
    asyncio.run(app.connect({"token": "t"}))

    result = asyncio.run(app.sync())

    assert [call[2] for call in api.calls if call[0] == "pulls"] == [github.QUERIES]
    assert result.complete and [t.key for t in result.topics] == ["2", "1"]


def test_a_partial_answer_makes_a_partial_sync_that_keeps_the_other_topics(tmp_path, keyring):
    app = connector(tmp_path, keyring, FakeApi(found=[pull(1)], complete=False))
    asyncio.run(app.connect({"token": "t"}))

    result = asyncio.run(app.sync())

    assert ([t.key for t in result.topics], result.complete, result.removed) == (["1"], False, [])


def test_a_rejected_token_on_sync_is_forgotten(tmp_path, keyring):
    api = FakeApi()
    app = connector(tmp_path, keyring, api)
    asyncio.run(app.connect({"token": "t"}))
    api.found = AuthError("github", "Rejected.")

    with pytest.raises(AuthError, match="Connect again"):
        asyncio.run(app.sync())
    assert keyring.get("github-token") is None


def test_github_cannot_reply_or_delete(tmp_path, keyring):
    app = connector(tmp_path, keyring, FakeApi())
    with pytest.raises(Unsupported):
        asyncio.run(app.reply("1", "Thanks"))
    with pytest.raises(Unsupported):
        asyncio.run(app.delete_topic("1"))


def http_api(handler) -> GitHubHttpApi:
    return GitHubHttpApi(HttpsClient(transport=httpx.MockTransport(handler)))


def test_the_http_adapter_sends_one_graphql_query_and_reads_every_search():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        node = {
            "databaseId": 9,
            "number": 4,
            "title": "Add retries",
            "url": "https://github.com/acme/web/pull/4",
            "updatedAt": "2026-10-24T09:00:00Z",
            "isDraft": False,
            "state": "OPEN",
            "merged": False,
            "reviewDecision": "CHANGES_REQUESTED",
            "author": {"login": "bo"},
            "repository": {"nameWithOwner": "acme/web"},
            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
        }
        data = {"reviewRequested": {"nodes": []}, "assigned": {"nodes": [node, {}]}, "authored": {"nodes": []}}
        return httpx.Response(200, json={"data": data})

    result = asyncio.run(http_api(handler).open_pull_requests("https://api.github.com/graphql", "t", github.QUERIES))
    [found] = result.pulls
    assert result.complete

    assert found == PullRequest(
        9,
        "acme/web",
        4,
        "Add retries",
        Reason.ASSIGNED,
        "bo",
        False,
        "https://github.com/acme/web/pull/4",
        "2026-10-24T09:00:00Z",
        checks="SUCCESS",
        review="CHANGES_REQUESTED",
    )
    [request] = seen
    assert (request.method, str(request.url)) == ("POST", "https://api.github.com/graphql")
    assert request.headers["Authorization"] == "Bearer t"
    variables = json.loads(request.content)["variables"]
    assert variables == {"first": 50} | {reason.value: query for query, reason in github.QUERIES}


NODE = {
    "databaseId": 9,
    "number": 4,
    "title": "Add retries",
    "url": "https://github.com/acme/web/pull/4",
    "isDraft": True,
    "state": "OPEN",
    "commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]},
}
SAML = [{"type": "FORBIDDEN", "message": "Resource protected by SAML."}]


@pytest.mark.parametrize(
    ("answer", "found"),
    [
        ({"data": {"reviewRequested": {"nodes": []}, "assigned": {"nodes": [None, NODE]}, "authored": {"nodes": []}},
          "errors": SAML}, (1, False)),
        ({"data": {"reviewRequested": {"nodes": [None]}, "assigned": {"nodes": [None]}, "authored": {"nodes": []}},
          "errors": SAML}, (0, False)),
        ({"data": {"reviewRequested": {"nodes": []}, "assigned": {"nodes": [NODE]}, "authored": {"nodes": []}}},
         (1, True)),
        ({"data": None, "errors": SAML}, RemoteError),
        ({"data": {"reviewRequested": None, "assigned": {"nodes": [NODE]}, "authored": {"nodes": []}},
          "errors": SAML}, RemoteError),
        ({"data": {"reviewRequested": {"nodes": []}, "assigned": {"nodes": []}}}, NetworkError),
    ],
)  # fmt: skip
def test_graphql_errors_make_a_partial_answer_or_fail_a_missing_search(answer, found):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer)

    pulls = http_api(handler).open_pull_requests("https://api.github.com/graphql", "t", github.QUERIES)
    if isinstance(found, tuple):
        result = asyncio.run(pulls)
        assert (len(result.pulls), result.complete) == found
    else:
        with pytest.raises(found, match="SAML" if found is RemoteError else "could not be read"):
            asyncio.run(pulls)


@pytest.mark.parametrize(
    ("status", "body", "error", "match"),
    [
        (401, {"message": "Bad credentials"}, AuthError, "rejected the token"),
        (404, {"message": "Not Found"}, AuthError, "No GitHub API"),
        (503, {"message": "Unavailable"}, RemoteError, "503: Unavailable"),
        (200, "not json", NetworkError, "could not be read"),
    ],
)
def test_the_http_adapter_reports_errors_by_kind(status, body, error, match):
    def handler(request: httpx.Request) -> httpx.Response:
        content = body if isinstance(body, str) else json.dumps(body)
        return httpx.Response(status, content=content.encode())

    with pytest.raises(error, match=match):
        asyncio.run(http_api(handler).me("https://api.github.com", "t"))
