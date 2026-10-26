"""The Jira connector: its rules, its use cases and its HTTP adapter."""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.https_client import HttpsClient
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.jira.adapters.jira_http import JiraHttpApi
from silentdesk.apps.jira.adapters.keyring_credentials import KeyringCredentials
from silentdesk.apps.jira.adapters.sqlcipher_state_store import SqlcipherStateStore
from silentdesk.apps.jira.application.jira import Jira
from silentdesk.apps.jira.core import jira
from silentdesk.apps.jira.domain.jira import Credential, Endpoint, Flavor, Issue, JiraAccount, JiraUser
from silentdesk.apps.jira.ports.jira_api import JiraApi
from silentdesk.contract import AuthError, Direction, RemoteError, StatusCategory, TopicStatus

SITE = "https://acme.atlassian.net"
ANA = JiraUser("acc-ana", "Ana Ruiz")


def test_sites_are_normalized_and_must_use_https():
    assert jira.normalize_site(" acme.atlassian.net/ ") == SITE
    assert jira.normalize_site("https://jira.acme.com:8443/jira/") == "https://jira.acme.com:8443/jira"
    with pytest.raises(AuthError, match="https"):
        jira.normalize_site("http://jira.acme.com")
    with pytest.raises(AuthError, match="not valid"):
        jira.normalize_site("")
    assert jira.is_cloud_site(SITE) and not jira.is_cloud_site("https://jira.acme.com")


@pytest.mark.parametrize(
    ("text", "utc"),
    [
        ("2026-10-23T10:00:00.000+0200", "2026-10-23T08:00:00Z"),
        ("2026-10-23T10:00:00.123-0530", "2026-10-23T15:30:00Z"),
        ("2026-10-23T10:00:00Z", "2026-10-23T10:00:00Z"),
        ("2026-10-23T10:00:00", ""),
        ("garbage", ""),
        (None, ""),
    ],
)
def test_jira_dates_become_rfc3339_in_utc(text, utc):
    assert jira.to_rfc3339(text) == utc


def issue(key: str, assignee: JiraUser | None, summary: str = "Fix login") -> Issue:
    return Issue(
        key.lower(),
        key,
        summary,
        "To Do",
        "PAY",
        assignee,
        JiraUser("acc-bo", "Bo"),
        "2026-10-23T10:00:00.000+0200",
        status_category="new",
    )


def test_an_issue_is_inbound_when_assigned_to_the_user():
    account = JiraAccount("acc-ana", "Ana Ruiz", Endpoint(SITE, SITE, Flavor.CLOUD))
    mine = jira.topic(issue("PAY-1", ANA), account)
    waiting = jira.topic(issue("PAY-2", None, summary=" "), account)
    assert (mine.key, mine.title, mine.items[0].direction) == ("pay-1", "Fix login", Direction.INBOUND)
    assert (waiting.title, waiting.items[0].direction) == ("PAY-2", Direction.OUTBOUND)
    assert waiting.items[0].url == f"{SITE}/browse/PAY-2"
    assert waiting.items[0].date == "2026-10-23T08:00:00Z"
    assert mine.status == TopicStatus("To Do", StatusCategory.NEW)


@pytest.mark.parametrize(
    ("name", "category", "expected"),
    [
        ("To Do", "new", TopicStatus("To Do", StatusCategory.NEW)),
        ("Code Review", "indeterminate", TopicStatus("Code Review", StatusCategory.IN_PROGRESS)),
        ("Closed", "done", TopicStatus("Closed", StatusCategory.DONE)),
        ("Triage", "undefined", TopicStatus("Triage", None)),
        ("Triage", None, TopicStatus("Triage", None)),
        (" In Progress ", "indeterminate", TopicStatus("In Progress", StatusCategory.IN_PROGRESS)),
        ("", "new", None),
        ("  ", None, None),
    ],
)
def test_an_issue_status_keeps_its_name_and_maps_its_category(name, category, expected):
    assert jira.status(name, category) == expected


class FakeApi(JiraApi):
    """Accepts the token only at the API bases in `accepted`."""

    def __init__(self, accepted: set[str], cloud_id: str | None = "cloud-1", missing: bool = False):
        self.accepted, self._cloud_id, self.missing, self.calls = accepted, cloud_id, missing, []

    async def myself(self, endpoint, credential):
        self.calls.append(("myself", endpoint.api_base))
        if self.missing:
            raise RemoteError("jira", "Not found.", 404)
        if endpoint.api_base not in self.accepted:
            raise AuthError("jira", "Rejected.")
        return ANA

    async def cloud_id(self, site_base):
        self.calls.append(("cloud_id", site_base))
        return self._cloud_id

    async def open_issues(self, endpoint, credential, count):
        if endpoint.api_base not in self.accepted:
            raise AuthError("jira", "Rejected.")
        return [issue(f"PAY-{n}", ANA) for n in range(count + 5)]


@pytest.fixture
def keyring(tmp_path) -> FileKeyring:
    return FileKeyring(tmp_path / "keyring.json")


def connector(tmp_path, keyring, api: FakeApi) -> Jira:
    database = SqlcipherDatabase(tmp_path / "silentdesk.db", keyring)
    return Jira(
        api, KeyringCredentials(keyring), SqlcipherStateStore(database), lambda site: site, lambda: "https://gw"
    )


CLOUD = {"site": "acme.atlassian.net", "email": "ana@acme.com", "token": "t"}


def test_a_cloud_token_connects_at_the_site(tmp_path, keyring):
    status = asyncio.run(connector(tmp_path, keyring, FakeApi({SITE})).connect(CLOUD))
    assert (status.connected, status.account) == (True, "Ana Ruiz · acme.atlassian.net")
    assert json.loads(keyring.get("jira-credential")) == {"email": "ana@acme.com", "token": "t"}


def test_a_scoped_cloud_token_falls_back_to_the_gateway(tmp_path, keyring):
    api = FakeApi({"https://gw/cloud-1"})
    app = connector(tmp_path, keyring, api)
    asyncio.run(app.connect(CLOUD))
    assert api.calls == [("myself", SITE), ("cloud_id", SITE), ("myself", "https://gw/cloud-1")]
    assert len(asyncio.run(app.sync()).topics) == jira.SYNC_COUNT


@pytest.mark.parametrize(
    ("params", "api", "match"),
    [
        ({**CLOUD, "token": " "}, FakeApi({SITE}), "Enter an API token"),
        ({"site": "jira.acme.com", "token": "t"}, FakeApi(set()), "rejected the token"),
        (CLOUD, FakeApi(set(), cloud_id=None), "rejected the token"),
        (CLOUD, FakeApi(set(), missing=True), "No Jira was found"),
    ],
)
def test_failed_connections_store_nothing(tmp_path, keyring, params, api, match):
    with pytest.raises(AuthError, match=match):
        asyncio.run(connector(tmp_path, keyring, api).connect(params))
    assert keyring.get("jira-credential") is None


def test_a_rejected_token_on_sync_is_forgotten(tmp_path, keyring):
    api = FakeApi({SITE})
    app = connector(tmp_path, keyring, api)
    asyncio.run(app.connect(CLOUD))
    api.accepted = set()
    with pytest.raises(AuthError, match="Connect again"):
        asyncio.run(app.sync())
    assert keyring.get("jira-credential") is None


def http_api(handler) -> JiraHttpApi:
    return JiraHttpApi(HttpsClient(transport=httpx.MockTransport(handler)))


def test_cloud_uses_basic_auth_and_search_jql_data_center_bearer_and_search():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"issues": []})

    api = http_api(handler)
    asyncio.run(api.open_issues(Endpoint(SITE, SITE, Flavor.CLOUD), Credential("ana@acme.com", "t"), 10))
    asyncio.run(api.open_issues(Endpoint("https://j", "https://j", Flavor.DATA_CENTER), Credential(None, "p"), 10))

    cloud, data_center = seen
    assert cloud.url.path == "/rest/api/3/search/jql"
    assert cloud.headers["Authorization"] == "Basic " + base64.b64encode(b"ana@acme.com:t").decode()
    assert cloud.url.params["maxResults"] == "10"
    assert data_center.url.path == "/rest/api/2/search"
    assert data_center.headers["Authorization"] == "Bearer p"


def test_the_http_adapter_reads_users_issues_and_error_messages():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/myself"):
            return httpx.Response(200, json={"accountId": "acc-ana", "displayName": "Ana Ruiz"})
        if request.url.path.endswith("/tenant_info"):
            return httpx.Response(200, json={"cloudId": "c-1"})
        return httpx.Response(400, json={"errorMessages": ["The JQL is wrong."]})

    api = http_api(handler)
    endpoint = Endpoint(SITE, SITE, Flavor.CLOUD)
    assert asyncio.run(api.myself(endpoint, Credential("a", "t"))) == ANA
    assert asyncio.run(api.cloud_id(SITE)) == "c-1"
    with pytest.raises(RemoteError, match="400: The JQL is wrong."):
        asyncio.run(api.open_issues(endpoint, Credential("a", "t"), 10))
