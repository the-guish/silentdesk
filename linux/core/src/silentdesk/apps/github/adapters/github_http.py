"""GitHub's REST API. Works with github.com and GitHub Enterprise Server."""

from __future__ import annotations

import json
from typing import Any

from ....contract import AuthError, Http, NetworkError, RemoteError
from ..domain.github import PullRequest, Reason
from ..ports.github_api import GitHubApi, Me

SERVICE = "github"
API_VERSION = "2022-11-28"
# Most open pull requests kept per query. Search pages hold up to 100.
PER_QUERY = "50"


class GitHubHttpApi(GitHubApi):
    def __init__(self, http: Http) -> None:
        self.http = http

    async def _get(self, url: str, token: str, params: dict[str, str] | None = None) -> Any:
        response = await self.http.request(
            "GET",
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )
        try:
            body = json.loads(response.body) if response.body else None
        except ValueError:
            body = None
        if response.status == 401:
            raise AuthError(SERVICE, "GitHub rejected the token. Check it, and its expiry.")
        if not 200 <= response.status < 300:
            message = body.get("message") if isinstance(body, dict) else None
            raise RemoteError(
                SERVICE, f"GitHub answered {response.status}: {message or 'no details'}.", response.status
            )
        if body is None:
            raise NetworkError(SERVICE, "GitHub's answer could not be read.")
        return body

    async def me(self, api_base: str, token: str) -> Me:
        try:
            user = await self._get(f"{api_base}/user", token)
            return Me(login=_string(user, "login"), name=user.get("name") or None)
        except RemoteError as error:
            if error.status == 404:
                raise AuthError(SERVICE, "No GitHub API was found there. Check the server address.") from error
            raise

    async def search(self, api_base: str, token: str, query: str, reason: Reason) -> list[PullRequest]:
        found = await self._get(
            f"{api_base}/search/issues",
            token,
            {"q": query, "sort": "updated", "order": "desc", "per_page": PER_QUERY},
        )
        items = found.get("items", []) if isinstance(found, dict) else None
        if not isinstance(items, list):
            raise NetworkError(SERVICE, "GitHub's search answer could not be read.")
        return [_pull_request(item, reason) for item in items]


def _string(value: Any, key: str) -> str:
    field = value.get(key) if isinstance(value, dict) else None
    if not isinstance(field, str):
        raise NetworkError(SERVICE, f"GitHub's answer has no {key}.")
    return field


def _pull_request(item: Any, reason: Reason) -> PullRequest:
    if not isinstance(item, dict) or not isinstance(item.get("id"), int) or not isinstance(item.get("number"), int):
        raise NetworkError(SERVICE, "GitHub's search answer could not be read.")
    user = item.get("user")
    # https://api.github.com/repos/acme/web -> acme/web
    repository_url = _string(item, "repository_url")
    return PullRequest(
        pr_id=item["id"],
        repo=repository_url.split("/repos/", 1)[-1],
        number=item["number"],
        title=item.get("title") or "",
        reason=reason,
        author=user.get("login", "") if isinstance(user, dict) else "",
        draft=item.get("draft") is True,
        url=_string(item, "html_url"),
        updated=item.get("updated_at") or "",
    )
