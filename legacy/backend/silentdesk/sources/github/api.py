"""GitHub REST calls, read-only. Works with github.com and GitHub Enterprise
Server, using a personal access token (fine-grained or classic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ...adapters import rest
from ...adapters.http import send
from ...core import errors
from ...core.model import Direction, GitHubEndpoint, PullRequestReason

API_VERSION = "2022-11-28"
# Most open pull requests kept per query. Search pages hold up to 100.
PER_QUERY = "50"


def direction(reason: PullRequestReason) -> Direction:
    if reason == PullRequestReason.AUTHORED:
        return Direction.OUTBOUND
    return Direction.INBOUND


# Open pull requests that ask something of the user, then the user's own.
# Each query must name `is:pr`; GitHub's search rejects queries without a
# type. `review-requested` includes requests made to the user's teams.
QUERIES: list[tuple[str, PullRequestReason]] = [
    ("is:pr is:open archived:false review-requested:@me", PullRequestReason.REVIEW_REQUESTED),
    ("is:pr is:open archived:false assignee:@me", PullRequestReason.ASSIGNED),
    ("is:pr is:open archived:false author:@me", PullRequestReason.AUTHORED),
]


def endpoint_for_server(server: str | None) -> GitHubEndpoint:
    """No server means github.com. Otherwise a GitHub Enterprise Server host
    such as `github.acme.com`; plain `http` is refused."""
    server = server.strip() if server is not None else None
    if not server:
        return GitHubEndpoint(api_base="https://api.github.com", web_base="https://github.com")
    with_scheme = server if "://" in server else f"https://{server}"

    def invalid() -> errors.Auth:
        return errors.Auth("the GitHub server address is not valid.")

    parsed = rest.parse_url(with_scheme)
    if parsed is None:
        raise invalid()
    if parsed.scheme != "https":
        raise errors.Auth("the GitHub server must use https://.")
    if parsed.host is None:
        raise invalid()
    if parsed.host in ("github.com", "api.github.com"):
        return endpoint_for_server(None)
    port = f":{parsed.port}" if parsed.port is not None else ""
    web_base = f"https://{parsed.host}{port}"
    return GitHubEndpoint(api_base=f"{web_base}/api/v3", web_base=web_base)


def host(endpoint: GitHubEndpoint) -> str:
    web_base = endpoint.web_base
    while web_base.startswith("https://"):
        web_base = web_base[len("https://") :]
    return web_base


@dataclass
class Me:
    login: str
    name: str


@dataclass
class PullMeta:
    pr_id: int
    repo: str
    number: int
    title: str
    reason: PullRequestReason
    direction: Direction
    draft: bool
    author: str
    url: str
    date: str


@dataclass
class RawUser:
    login: str
    name: str | None


@dataclass
class RawItem:
    id: int
    number: int
    title: str
    html_url: str
    repository_url: str
    # The author's login.
    user: str | None
    draft: bool
    updated_at: str


def _read_user(value: Any) -> RawUser:
    o = rest.obj(value)
    return RawUser(login=rest.string(o, "login"), name=rest.opt_string(o, "name"))


def _read_login(value: Any) -> str:
    return rest.string(rest.obj(value), "login")


def read_item(value: Any) -> RawItem:
    o = rest.obj(value)
    return RawItem(
        id=rest.u64(o, "id"),
        number=rest.u64(o, "number"),
        title=rest.default_string(o, "title"),
        html_url=rest.string(o, "html_url"),
        repository_url=rest.string(o, "repository_url"),
        user=rest.opt(o, "user", _read_login),
        draft=rest.default_bool(o, "draft"),
        updated_at=rest.default_string(o, "updated_at"),
    )


def _read_search(value: Any) -> list[RawItem]:
    return rest.default_list(rest.obj(value), "items", read_item)


def _error_message(response: httpx.Response) -> str | None:
    try:
        return rest.read_body(response, lambda v: rest.opt_string(rest.obj(v), "message"))
    except ValueError:
        return None


async def get(http: httpx.AsyncClient, token: str, url: str, query: list[tuple[str, str]], read):
    response = await send(
        http,
        "GET",
        url,
        params=query or None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    status = response.status_code
    if 200 <= status < 300:
        return rest.decode(response, read)
    if status == 401:
        raise errors.Reauthorize("GitHub")
    message = _error_message(response)
    raise errors.Api("GitHub", status, message if message is not None else rest.reason(status))


async def connect(http: httpx.AsyncClient, endpoint: GitHubEndpoint, token: str) -> Me:
    """Checks the token and identifies the user."""
    try:
        user: RawUser = await get(http, token, f"{endpoint.api_base}/user", [], _read_user)
    except errors.Reauthorize:
        raise errors.Auth("GitHub rejected the token. Check it, and its expiry.") from None
    except errors.Api as e:
        if e.status == 404:
            raise errors.Auth(f"no GitHub API was found at {host(endpoint)}. Check the server address.") from None
        raise
    name = user.name if user.name is not None and user.name.strip() else user.login
    return Me(login=user.login, name=name)


async def open_pull_requests(http: httpx.AsyncClient, endpoint: GitHubEndpoint, token: str) -> list[PullMeta]:
    """Open pull requests that request the user's review, are assigned to
    the user, or were opened by the user, most recently updated first."""
    url = f"{endpoint.api_base}/search/issues"
    found: list[tuple[RawItem, PullRequestReason]] = []
    for query, reason in QUERIES:
        items: list[RawItem] = await get(
            http,
            token,
            url,
            [("q", query), ("sort", "updated"), ("order", "desc"), ("per_page", PER_QUERY)],
            _read_search,
        )
        found.extend((item, reason) for item in items)
    return merge(found)


def merge(found: list[tuple[RawItem, PullRequestReason]]) -> list[PullMeta]:
    """One entry per pull request. When a pull request matches several
    queries, the first reason wins: a review request outranks an assignment,
    which outranks authorship."""
    by_id: dict[int, PullMeta] = {}
    for item, reason in found:
        if item.id not in by_id:
            by_id[item.id] = to_meta(item, reason)
    pulls = sorted(by_id.values(), key=lambda p: p.pr_id)
    # Stable: equal dates keep the pr_id order.
    pulls.sort(key=lambda p: p.date, reverse=True)
    return pulls


def to_meta(item: RawItem, reason: PullRequestReason) -> PullMeta:
    return PullMeta(
        repo=repo_name(item.repository_url),
        reason=reason,
        direction=direction(reason),
        author=item.user or "",
        title=item.title.strip(),
        pr_id=item.id,
        number=item.number,
        draft=item.draft,
        url=item.html_url,
        date=item.updated_at,
    )


def repo_name(repository_url: str) -> str:
    """`https://api.github.com/repos/acme/web` → `acme/web`."""
    parts = repository_url.split("/repos/")
    return parts[1] if len(parts) > 1 else repository_url
