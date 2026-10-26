"""Jira's REST API: Jira Cloud (email and API token, scoped or not) and Jira
Data Center (personal access token)."""

from __future__ import annotations

import base64
import json
from typing import Any

from ....contract import AuthError, Http, NetworkError, RemoteError
from ..domain.jira import Credential, Endpoint, Flavor, Issue, JiraUser
from ..ports.jira_api import JiraApi

SERVICE = "jira"
# Open issues assigned to or reported by the user, most recently updated first.
JQL = "(assignee = currentUser() OR reporter = currentUser()) AND statusCategory != Done ORDER BY updated DESC"
FIELDS = "summary,status,assignee,reporter,updated,project"


def _authorization(credential: Credential) -> str:
    if credential.email:
        pair = f"{credential.email}:{credential.token}".encode()
        return "Basic " + base64.b64encode(pair).decode()
    return f"Bearer {credential.token}"


def _url(endpoint: Endpoint, path: str) -> str:
    return f"{endpoint.api_base}/rest/api/{'3' if endpoint.flavor == Flavor.CLOUD else '2'}/{path}"


def _json(body: bytes) -> Any:
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


def _user(value: Any) -> JiraUser | None:
    if not isinstance(value, dict):
        return None
    id = next((v for v in (value.get("accountId"), value.get("key"), value.get("name")) if isinstance(v, str)), None)
    return JiraUser(id=id, name=value.get("displayName") or "")


def _issue(value: Any) -> Issue:
    fields = value.get("fields") if isinstance(value, dict) else None
    if not isinstance(fields, dict) or not isinstance(value.get("id"), str) or not isinstance(value.get("key"), str):
        raise NetworkError(SERVICE, "Jira's search answer could not be read.")
    status, project = fields.get("status"), fields.get("project")
    return Issue(
        issue_id=value["id"],
        key=value["key"],
        summary=fields.get("summary") or "",
        status=status.get("name", "") if isinstance(status, dict) else "",
        project=project.get("key", "") if isinstance(project, dict) else "",
        assignee=_user(fields.get("assignee")),
        reporter=_user(fields.get("reporter")),
        updated=fields.get("updated") if isinstance(fields.get("updated"), str) else None,
        status_category=_status_category(status),
    )


def _status_category(status: Any) -> str | None:
    category = status.get("statusCategory") if isinstance(status, dict) else None
    key = category.get("key") if isinstance(category, dict) else None
    return key if isinstance(key, str) else None


class JiraHttpApi(JiraApi):
    def __init__(self, http: Http) -> None:
        self.http = http

    async def _get(self, url: str, credential: Credential, params: dict[str, str] | None = None) -> Any:
        response = await self.http.request(
            "GET",
            url,
            params=params,
            headers={"Accept": "application/json", "Authorization": _authorization(credential)},
        )
        body = _json(response.body)
        if response.status == 401:
            raise AuthError(SERVICE, "Jira rejected the token.")
        if not 200 <= response.status < 300:
            messages = body.get("errorMessages") if isinstance(body, dict) else None
            message = messages[0] if isinstance(messages, list) and messages else None
            message = message or (body.get("message") if isinstance(body, dict) else None)
            raise RemoteError(SERVICE, f"Jira answered {response.status}: {message or 'no details'}.", response.status)
        if body is None:
            raise NetworkError(SERVICE, "Jira's answer could not be read.")
        return body

    async def myself(self, endpoint: Endpoint, credential: Credential) -> JiraUser:
        user = _user(await self._get(_url(endpoint, "myself"), credential))
        if user is None:
            raise NetworkError(SERVICE, "Jira's answer could not be read.")
        return user

    async def cloud_id(self, site_base: str) -> str | None:
        response = await self.http.request("GET", f"{site_base}/_edge/tenant_info")
        body = _json(response.body) if 200 <= response.status < 300 else None
        cloud_id = body.get("cloudId") if isinstance(body, dict) else None
        return cloud_id if isinstance(cloud_id, str) else None

    async def open_issues(self, endpoint: Endpoint, credential: Credential, count: int) -> list[Issue]:
        # Jira Cloud replaced /search with /search/jql; Data Center keeps /search.
        path = "search/jql" if endpoint.flavor == Flavor.CLOUD else "search"
        found = await self._get(
            _url(endpoint, path), credential, {"jql": JQL, "maxResults": str(count), "fields": FIELDS}
        )
        issues = found.get("issues", []) if isinstance(found, dict) else None
        if not isinstance(issues, list):
            raise NetworkError(SERVICE, "Jira's search answer could not be read.")
        return [_issue(issue) for issue in issues]
