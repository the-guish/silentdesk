import asyncio
import base64
import json

import httpx
import pytest

from silentdesk.adapters import rest
from silentdesk.core import errors
from silentdesk.core.model import (
    Direction,
    JiraAccount,
    JiraEndpoint,
    JiraFlavor,
    JiraIssue,
    Topic,
    VaultData,
)
from silentdesk.core.secret_names import JIRA_CREDENTIAL
from silentdesk.sources.jira import JiraSource, api, domain
from silentdesk.sources.jira.api import GATEWAY, Credential, IssueMeta

from .fakes import make_host, mock_client

# --- Ported from src-tauri/src/jira/mod.rs --------------------------------


def meta(id: str, key: str, summary: str) -> IssueMeta:
    return IssueMeta(
        issue_id=id,
        key=key,
        summary=summary,
        direction=Direction.INBOUND,
        status="Open",
        project="PAY",
        assignee="Luis",
        reporter="Ana",
        url=f"https://acme.atlassian.net/browse/{key}",
        date="2026-10-23T10:00:00Z",
    )


def test_each_issue_gets_its_own_topic():
    data = VaultData()
    domain.apply_sync(data, [meta("1", "PAY-1", "Refunds"), meta("2", "PAY-2", "")], "now")
    assert [t.title for t in data.topics] == ["Refunds", "PAY-2"]


def test_resync_keeps_topics_and_drops_closed_issues():
    data = VaultData()
    domain.apply_sync(data, [meta("1", "PAY-1", "A"), meta("2", "PAY-2", "B")], "now")
    topic_of_b = data.jira_issues[1].topic_id
    domain.apply_sync(data, [meta("2", "PAY-2", "B"), meta("3", "PAY-3", "C")], "later")
    assert data.jira_issues[0].topic_id == topic_of_b
    assert len(data.topics) == 2
    assert all(t.title != "A" for t in data.topics)

    domain.clear(data)
    assert data.topics == []


# --- Ported from src-tauri/src/jira/api.rs --------------------------------


def issue(text: str) -> api.RawIssue:
    return api.read_issue(json.loads(text))


def test_normalizes_sites():
    assert api.normalize_site("acme.atlassian.net") == "https://acme.atlassian.net"
    assert api.normalize_site(" https://acme.atlassian.net/ ") == "https://acme.atlassian.net"
    assert api.normalize_site("https://jira.corp.example:8443/jira/") == "https://jira.corp.example:8443/jira"
    with pytest.raises(errors.Auth):
        api.normalize_site("http://jira.corp.example")
    with pytest.raises(errors.Auth):
        api.normalize_site("https://")


def test_recognizes_cloud_sites():
    assert api.is_cloud_site("https://acme.atlassian.net")
    assert not api.is_cloud_site("https://jira.corp.example")


def test_builds_versioned_urls():
    cloud = JiraEndpoint("https://acme.atlassian.net", f"{GATEWAY}/abc", JiraFlavor.CLOUD)
    assert api.url(cloud, "search/jql") == "https://api.atlassian.com/ex/jira/abc/rest/api/3/search/jql"
    dc = JiraEndpoint("https://jira.corp.example/jira", "https://jira.corp.example/jira", JiraFlavor.DATA_CENTER)
    assert api.url(dc, "myself") == "https://jira.corp.example/jira/rest/api/2/myself"


def test_parses_cloud_issue_assigned_to_me():
    m = api.to_meta(
        issue(
            """{"id":"10001","key":"PAY-42","fields":{
                "summary":" Refund fails for EUR ","status":{"name":"In Progress"},
                "project":{"key":"PAY"},
                "assignee":{"accountId":"me-1","displayName":"Luis Castro"},
                "reporter":{"accountId":"ana-2","displayName":"Ana Ruiz"},
                "updated":"2026-10-23T12:00:00.000+0200"}}"""
        ),
        "me-1",
        "https://acme.atlassian.net",
    )
    assert m.direction == Direction.INBOUND
    assert m.summary == "Refund fails for EUR"
    assert m.status == "In Progress"
    assert m.reporter == "Ana Ruiz"
    assert m.url == "https://acme.atlassian.net/browse/PAY-42"
    assert m.date == "2026-10-23T10:00:00Z"


def test_parses_data_center_issue_reported_by_me_and_unassigned():
    m = api.to_meta(
        issue(
            """{"id":"2","key":"OPS-7","fields":{"summary":"Rotate certs",
                "status":{"name":"Open"},"assignee":null,
                "reporter":{"key":"JIRAUSER10","name":"luis","displayName":"Luis"},
                "updated":"2026-10-22T08:30:00.000+0000"}}"""
        ),
        "JIRAUSER10",
        "https://jira.corp.example",
    )
    assert m.direction == Direction.OUTBOUND
    assert m.assignee == ""
    assert m.project == ""
    assert m.date == "2026-10-22T08:30:00Z"


def test_credential_round_trips_as_json():
    c = Credential(email="me@example.com", token="t")
    assert Credential.from_secret(c.to_secret()) == c


# --- Beyond the Rust tests ------------------------------------------------


def test_credential_is_stored_as_serde_json_wrote_it():
    assert Credential("me@example.com", "t").to_secret() == '{"email":"me@example.com","token":"t"}'
    assert Credential(None, "ñ").to_secret() == '{"email":null,"token":"ñ"}'
    assert Credential.from_secret('{"token":"t"}') == Credential(None, "t")
    assert Credential.from_secret("not json") is None
    assert Credential.from_secret('{"email":"e"}') is None


def test_site_normalization_follows_the_url_crate():
    n = api.normalize_site
    assert n("HTTPS://Acme.Atlassian.NET:443/") == "https://acme.atlassian.net"
    assert n("https://user:pw@jira.corp.example/a/./b/../jira/?q=1#f") == "https://jira.corp.example/a/jira"
    assert n("https://jira.corp.example/my jira") == "https://jira.corp.example/my%20jira"
    assert n("https://[0:0::1]:8443") == "https://[::1]:8443"
    assert n("https://10.0.0.1") == "https://10.0.0.1"
    assert n("https://bücher.de") == "https://xn--bcher-kva.de"
    for bad in ["https://acme atlassian.net", "https://x:99999", "https://x:abc", "https://[::1", "", "x/?a=://"]:
        with pytest.raises(errors.Auth, match="the Jira site address is not valid."):
            n(bad)
    for not_https in ["http://jira.corp.example", "ftp://jira.corp.example", "file:///etc"]:
        with pytest.raises(errors.Auth, match="must use https"):
            n(not_https)


def test_url_parser_hosts():
    assert rest.parse_url("https://0x7f.1/").host == "127.0.0.1"
    assert rest.parse_url("https://1.2.3.256") is None
    assert rest.parse_url("https://[2001:db8:0:0:1:0:0:1]").host == "[2001:db8::1:0:0:1]"
    assert rest.parse_url("https://a%2fb") is None
    assert rest.parse_url("https:\\\\h\\p").host == "h"
    assert rest.parse_url("https://h:8080").port == 8080


def test_dates():
    assert api.to_rfc3339("2026-10-23T10:00:00.120-0130") == "2026-10-23T11:30:00.12Z"
    assert api.to_rfc3339("2026-10-23T10:00:00+02:00") == "2026-10-23T08:00:00Z"
    assert api.to_rfc3339("2026-10-23T10:00:00.5z") == "2026-10-23T10:00:00.5Z"
    assert api.to_rfc3339("2026-10-23T10:00:00+0200") == ""
    assert api.to_rfc3339("2026-02-30T10:00:00.000+0000") == ""
    assert api.to_rfc3339("yesterday") == ""


def test_issue_with_wrong_shape_is_refused():
    with pytest.raises(rest.Invalid):
        issue('{"id":1,"key":"K","fields":{}}')
    with pytest.raises(rest.Invalid):
        issue('{"id":"1","key":"K","fields":{"summary":null}}')
    assert issue('{"id":"1","key":"K","fields":{}}').fields.summary == ""


# --- The source -----------------------------------------------------------

SITE = "https://acme.atlassian.net"
ME = {"accountId": "me-1", "displayName": "Luis Castro"}


def raw_issue(id: str, key: str, summary: str, assignee: str = "me-1") -> dict:
    return {
        "id": id,
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": "Open"},
            "project": {"key": key.split("-")[0]},
            "assignee": {"accountId": assignee, "displayName": assignee},
            "reporter": {"accountId": "ana", "displayName": "Ana"},
            "updated": "2026-10-23T12:00:00.000+0200",
        },
    }


def cloud_account(user_id: str = "me-1", site: str = SITE) -> JiraAccount:
    return JiraAccount(JiraEndpoint(site, site, JiraFlavor.CLOUD), user_id, "Luis Castro")


def connected(data: VaultData | None = None):
    data = data or VaultData(jira_account=cloud_account())
    secret = Credential("me@example.com", "tok").to_secret()
    return make_host(data, {JIRA_CREDENTIAL: secret})


class Recorder:
    """A mock Jira that answers by path and records each request."""

    def __init__(self, routes: dict[str, httpx.Response | object]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(f"{request.url.host}{request.url.path}")
        if route is None:
            return httpx.Response(404)
        return route() if callable(route) else route


def source(host, routes) -> tuple[JiraSource, Recorder]:
    recorder = Recorder(routes)
    return JiraSource(host, mock_client(recorder)), recorder


def basic(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def test_status_when_not_connected():
    s, _ = source(make_host(), {})
    status = asyncio.run(s.status())
    assert (status.configured, status.connected, status.account) == (True, False, None)


def test_connect_cloud_stores_credential_and_account():
    host = make_host()
    s, r = source(host, {"acme.atlassian.net/rest/api/3/myself": httpx.Response(200, json=ME)})
    status = asyncio.run(
        s.methods()["jira.connect"]({"site": "acme.atlassian.net/", "email": " me@example.com ", "token": " tok "})
    )
    assert (status.connected, status.account) == (True, "Luis Castro · acme.atlassian.net")
    assert r.requests[0].headers["authorization"] == basic("me@example.com", "tok")
    assert r.requests[0].headers["accept"] == "application/json"
    assert host.secrets.values[JIRA_CREDENTIAL] == '{"email":"me@example.com","token":"tok"}'
    assert host.store.data().jira_account == cloud_account()


def test_connect_scoped_token_goes_through_the_gateway():
    host = make_host()
    s, r = source(
        host,
        {
            "acme.atlassian.net/rest/api/3/myself": httpx.Response(401),
            "acme.atlassian.net/_edge/tenant_info": httpx.Response(200, json={"cloudId": "abc"}),
            "api.atlassian.com/ex/jira/abc/rest/api/3/myself": httpx.Response(200, json=ME),
        },
    )
    asyncio.run(s.connect({"site": SITE, "email": "me@example.com", "token": "tok"}))
    assert host.store.data().jira_account.endpoint == JiraEndpoint(SITE, f"{GATEWAY}/abc", JiraFlavor.CLOUD)
    assert "authorization" not in r.requests[1].headers


def test_connect_data_center_uses_bearer_and_v2():
    host = make_host()
    user = {"key": "JIRAUSER10", "name": "luis", "displayName": "Luis"}
    s, r = source(host, {"jira.corp.example/jira/rest/api/2/myself": httpx.Response(200, json=user)})
    status = asyncio.run(s.connect({"site": "jira.corp.example/jira", "email": None, "token": "pat"}))
    assert status.account == "Luis · jira.corp.example/jira"
    assert r.requests[0].headers["authorization"] == "Bearer pat"
    account = host.store.data().jira_account
    assert account.user_id == "JIRAUSER10"
    assert account.endpoint.flavor == JiraFlavor.DATA_CENTER
    assert json.loads(host.secrets.values[JIRA_CREDENTIAL]) == {"email": None, "token": "pat"}


def test_connect_failures_store_nothing():
    cases = [
        (
            {"jira.corp.example/rest/api/2/myself": httpx.Response(401)},
            "jira.corp.example",
            None,
            "Sign-in failed: Jira rejected the token. Check the site, email and API token.",
        ),
        (
            {},
            "jira.corp.example",
            None,
            "Sign-in failed: no Jira was found at https://jira.corp.example. Check the site address.",
        ),
        (
            {
                "acme.atlassian.net/rest/api/3/myself": httpx.Response(401),
                "acme.atlassian.net/_edge/tenant_info": httpx.Response(200, text="<html>"),
            },
            SITE,
            "e",
            "Sign-in failed: Jira rejected the token. Check the site, email and API token.",
        ),
        (
            {
                "acme.atlassian.net/rest/api/3/myself": httpx.Response(401),
                "acme.atlassian.net/_edge/tenant_info": httpx.Response(200, json={"cloudId": "abc"}),
                "api.atlassian.com/ex/jira/abc/rest/api/3/myself": httpx.Response(401),
            },
            SITE,
            "e",
            "Sign-in failed: Jira rejected the token. Check the site, email and API token.",
        ),
        (
            {"acme.atlassian.net/rest/api/3/myself": httpx.Response(200, json={"displayName": "x"})},
            SITE,
            "e",
            "Sign-in failed: Jira did not identify the user.",
        ),
        (
            {"acme.atlassian.net/rest/api/3/myself": httpx.Response(403, json={"errorMessages": ["No access"]})},
            SITE,
            "e",
            "Jira API error (403): No access",
        ),
        (
            {"acme.atlassian.net/rest/api/3/myself": httpx.Response(503, text="down")},
            SITE,
            "e",
            "Jira API error (503): Service Unavailable",
        ),
    ]
    for routes, site, email, message in cases:
        host = make_host()
        s, _ = source(host, routes)
        with pytest.raises(errors.AppError) as e:
            asyncio.run(s.connect({"site": site, "email": email, "token": "tok"}))
        assert str(e.value) == message
        assert host.secrets.values == {} and host.store.writes == 0


def test_connect_checks_input_before_any_request():
    for params, message in [
        ({"site": "http://jira.corp.example", "token": "t"}, "Sign-in failed: the Jira site must use https://."),
        ({"site": SITE, "token": "  "}, "Sign-in failed: enter an API token."),
    ]:
        s, r = source(make_host(), {})
        with pytest.raises(errors.Auth) as e:
            asyncio.run(s.connect(params))
        assert str(e.value) == message
        assert r.requests == []


def test_connect_as_another_account_clears_old_data():
    old = VaultData(
        topics=[Topic("t1", "Old", "2026-01-01T00:00:00Z")],
        jira_account=cloud_account(user_id="someone-else"),
        jira_issues=[JiraIssue("9", "OLD-9", "t1", Direction.INBOUND, "", "", "", "", "", "d")],
    )
    host = make_host(old)
    s, _ = source(host, {"acme.atlassian.net/rest/api/3/myself": httpx.Response(200, json=ME)})
    asyncio.run(s.connect({"site": SITE, "email": "me@example.com", "token": "tok"}))
    data = host.store.data()
    assert data.jira_issues == [] and data.topics == []
    assert data.jira_account.user_id == "me-1"


def test_reconnecting_the_same_account_keeps_data():
    old = VaultData(
        topics=[Topic("t1", "Old", "2026-01-01T00:00:00Z")],
        jira_account=cloud_account(),
        jira_issues=[JiraIssue("9", "OLD-9", "t1", Direction.INBOUND, "", "", "", "", "", "d")],
    )
    host = make_host(old)
    s, _ = source(host, {"acme.atlassian.net/rest/api/3/myself": httpx.Response(200, json=ME)})
    asyncio.run(s.connect({"site": SITE, "email": "me@example.com", "token": "tok"}))
    assert [t.id for t in host.store.data().topics] == ["t1"]


def test_sync_maps_issues_to_topics():
    host = connected()
    issues = [raw_issue("1", "PAY-1", " Refunds "), raw_issue("2", "OPS-2", "", assignee="bob")]
    s, r = source(host, {"acme.atlassian.net/rest/api/3/search/jql": httpx.Response(200, json={"issues": issues})})
    views = asyncio.run(s.methods()["jira.sync"]({}))
    params = r.requests[0].url.params
    assert params["jql"] == api.JQL
    assert params["maxResults"] == "10"
    assert params["fields"] == "summary,status,assignee,reporter,updated,project"
    assert sorted(v["title"] for v in views) == ["OPS-2", "Refunds"]
    data = host.store.data()
    assert [(i.key, i.direction) for i in data.jira_issues] == [
        ("PAY-1", Direction.INBOUND),
        ("OPS-2", Direction.OUTBOUND),
    ]
    assert data.jira_issues[0].date == "2026-10-23T10:00:00Z"
    assert views[0]["jiraIssues"][0]["url"].startswith(f"{SITE}/browse/")


def test_sync_keeps_at_most_ten_and_data_center_uses_search():
    site = "https://jira.corp.example"
    data = VaultData(jira_account=JiraAccount(JiraEndpoint(site, site, JiraFlavor.DATA_CENTER), "me-1", "Luis"))
    host = make_host(data, {JIRA_CREDENTIAL: Credential(None, "pat").to_secret()})
    issues = [raw_issue(str(n), f"OPS-{n}", f"Issue {n}") for n in range(12)]
    s, r = source(host, {"jira.corp.example/rest/api/2/search": httpx.Response(200, json={"issues": issues})})
    asyncio.run(s.sync())
    assert len(host.store.data().jira_issues) == 10
    assert r.requests[0].headers["authorization"] == "Bearer pat"


def test_sync_when_not_connected():
    for host in [make_host(), make_host(VaultData(jira_account=cloud_account()))]:
        s, _ = source(host, {})
        with pytest.raises(errors.NotConnected):
            asyncio.run(s.sync())


def test_sync_with_revoked_token_forgets_it_and_keeps_topics():
    host = connected()
    s, _ = source(
        host,
        {
            "acme.atlassian.net/rest/api/3/search/jql": httpx.Response(
                200, json={"issues": [raw_issue("1", "PAY-1", "A")]}
            )
        },
    )
    asyncio.run(s.sync())
    s.http = mock_client(lambda request: httpx.Response(401))
    with pytest.raises(errors.Reauthorize) as e:
        asyncio.run(s.sync())
    assert str(e.value) == "Jira access was revoked or has expired. Connect again."
    assert JIRA_CREDENTIAL not in host.secrets.values
    assert [t.title for t in host.store.data().topics] == ["A"]
    status = asyncio.run(s.status())
    assert (status.connected, status.account) == (False, "Luis Castro · acme.atlassian.net")


def test_sync_errors():
    def unreachable(request):
        raise httpx.ConnectError("connection refused", request=request)

    for handler, kind in [
        (unreachable, errors.Network),
        (lambda request: httpx.Response(200, text="not json"), errors.Network),
        (lambda request: httpx.Response(200, json={"issues": [{"id": "1"}]}), errors.Network),
        (lambda request: httpx.Response(400, json={"message": "Bad JQL"}), errors.Api),
    ]:
        host = connected()
        s = JiraSource(host, mock_client(handler))
        with pytest.raises(kind) as e:
            asyncio.run(s.sync())
        if kind is errors.Api:
            assert str(e.value) == "Jira API error (400): Bad JQL"
        elif handler is not unreachable:
            assert str(e.value) == "Network error: error decoding response body"
        assert JIRA_CREDENTIAL in host.secrets.values


def test_disconnect_forgets_everything():
    host = connected()
    s, _ = source(
        host,
        {
            "acme.atlassian.net/rest/api/3/search/jql": httpx.Response(
                200, json={"issues": [raw_issue("1", "PAY-1", "A")]}
            )
        },
    )
    asyncio.run(s.sync())
    status = asyncio.run(s.methods()["jira.disconnect"]({}))
    assert (status.connected, status.account) == (False, None)
    assert host.secrets.values == {}
    data = host.store.data()
    assert data.jira_account is None and data.jira_issues == [] and data.topics == []


def test_methods_are_named_for_the_ui():
    s, _ = source(make_host(), {})
    assert sorted(s.methods()) == ["jira.connect", "jira.disconnect", "jira.status", "jira.sync"]


def test_missing_argument():
    s, _ = source(make_host(), {})
    with pytest.raises(errors.AppError, match="`token` is missing"):
        asyncio.run(s.connect({"site": SITE}))
