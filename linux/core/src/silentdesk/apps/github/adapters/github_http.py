"""GitHub's REST and GraphQL APIs. Works with github.com and GitHub
Enterprise Server."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ....contract import AuthError, Http, NetworkError, RemoteError
from ..domain.github import PullRequest, Reason
from ..ports.github_api import GitHubApi, Me

SERVICE = "github"
API_VERSION = "2022-11-28"
# Most open pull requests kept per query. Search pages hold up to 100.
PER_QUERY = 50
# One search per reason, each named after it, with what the chip needs.
PULL_REQUESTS = """
query($reviewRequested: String!, $assigned: String!, $authored: String!, $first: Int!) {
  reviewRequested: search(query: $reviewRequested, type: ISSUE, first: $first) { ...pulls }
  assigned: search(query: $assigned, type: ISSUE, first: $first) { ...pulls }
  authored: search(query: $authored, type: ISSUE, first: $first) { ...pulls }
}
fragment pulls on SearchResultItemConnection {
  nodes {
    ... on PullRequest {
      databaseId number title url updatedAt isDraft state merged reviewDecision
      author { login }
      repository { nameWithOwner }
      commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
    }
  }
}
"""


class GitHubHttpApi(GitHubApi):
    def __init__(self, http: Http) -> None:
        self.http = http

    async def _send(self, method: str, url: str, token: str, body: Any = None) -> Any:
        response = await self.http.request(
            method,
            url,
            json=body,
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
            user = await self._send("GET", f"{api_base}/user", token)
            return Me(login=_string(user, "login"), name=user.get("name") or None)
        except RemoteError as error:
            if error.status == 404:
                raise AuthError(SERVICE, "No GitHub API was found there. Check the server address.") from error
            raise

    async def open_pull_requests(
        self, graphql_url: str, token: str, queries: Sequence[tuple[str, Reason]]
    ) -> list[PullRequest]:
        variables: dict[str, Any] = {reason.value: query for query, reason in queries}
        variables["first"] = PER_QUERY
        found = await self._send("POST", graphql_url, token, {"query": PULL_REQUESTS, "variables": variables})
        # GitHub can answer with data and errors at once, such as for a
        # repository the token cannot read. Its pull requests come back
        # empty, and the others still count. Only a missing search fails the
        # sync, as dropping it would drop its pull requests' topics.
        errors = found.get("errors") if isinstance(found, dict) else None
        data = found.get("data") if isinstance(found, dict) else None
        pulls = []
        for _, reason in queries:
            search = data.get(reason.value) if isinstance(data, dict) else None
            nodes = search.get("nodes") if isinstance(search, dict) else None
            if not isinstance(nodes, list):
                if isinstance(errors, list) and errors:
                    message = errors[0].get("message") if isinstance(errors[0], dict) else None
                    raise RemoteError(SERVICE, f"GitHub answered: {message or 'an error'}.", 200)
                raise NetworkError(SERVICE, "GitHub's search answer could not be read.")
            # A search for pull requests can still hold an empty node, as for
            # a repository the token cannot read.
            pulls += [_pull_request(node, reason) for node in nodes if node]
        return pulls


def _string(value: Any, key: str) -> str:
    field = value.get(key) if isinstance(value, dict) else None
    if not isinstance(field, str):
        raise NetworkError(SERVICE, f"GitHub's answer has no {key}.")
    return field


def _pull_request(node: Any, reason: Reason) -> PullRequest:
    if (
        not isinstance(node, dict)
        or not isinstance(node.get("databaseId"), int)
        or not isinstance(node.get("number"), int)
    ):
        raise NetworkError(SERVICE, "GitHub's search answer could not be read.")
    author, repository = node.get("author"), node.get("repository")
    return PullRequest(
        pr_id=node["databaseId"],
        repo=repository.get("nameWithOwner", "") if isinstance(repository, dict) else "",
        number=node["number"],
        title=node.get("title") or "",
        reason=reason,
        author=author.get("login", "") if isinstance(author, dict) else "",
        draft=node.get("isDraft") is True,
        url=_string(node, "url"),
        updated=node.get("updatedAt") or "",
        merged=node.get("merged") is True,
        closed=node.get("state") in ("CLOSED", "MERGED"),
        checks=_checks(node),
        review=node.get("reviewDecision") if isinstance(node.get("reviewDecision"), str) else None,
    )


def _checks(node: dict[str, Any]) -> str | None:
    """The state GitHub sums up for the checks on the last commit."""
    commits = node.get("commits")
    last = commits.get("nodes") if isinstance(commits, dict) else None
    if not isinstance(last, list) or not last or not isinstance(last[-1], dict):
        return None
    commit = last[-1].get("commit")
    rollup = commit.get("statusCheckRollup") if isinstance(commit, dict) else None
    state = rollup.get("state") if isinstance(rollup, dict) else None
    return state if isinstance(state, str) else None
