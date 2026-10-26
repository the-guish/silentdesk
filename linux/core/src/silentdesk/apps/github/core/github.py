"""Rules about GitHub: which server, which pull requests, and their topics.
See docs/specs/integrations/github/github.md."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from ....contract import AuthError, Direction, Item, Topic
from ..domain.github import Endpoint, GitHubAccount, PullRequest, Reason

SERVICE = "github"
GITHUB_COM = Endpoint(api_base="https://api.github.com", web_base="https://github.com")

# Open pull requests that ask something of the user, then the user's own.
# Each query must name `is:pr`: GitHub's search rejects queries without a
# type. `review-requested` includes requests made to the user's teams.
QUERIES: list[tuple[str, Reason]] = [
    ("is:pr is:open archived:false review-requested:@me", Reason.REVIEW_REQUESTED),
    ("is:pr is:open archived:false assignee:@me", Reason.ASSIGNED),
    ("is:pr is:open archived:false author:@me", Reason.AUTHORED),
]


def endpoint_for_server(server: str | None) -> Endpoint:
    """No server means github.com. Otherwise a GitHub Enterprise Server host,
    such as github.acme.com; plain http is refused."""
    server = (server or "").strip()
    if not server:
        return GITHUB_COM
    url = urlsplit(server if "://" in server else f"https://{server}")
    if url.scheme != "https":
        raise AuthError(SERVICE, "The GitHub server must use https://.")
    try:
        host, port = url.hostname, url.port
    except ValueError:
        host = port = None
    if not host or url.username or url.password:
        raise AuthError(SERVICE, "The GitHub server address is not valid.")
    if host in ("github.com", "api.github.com"):
        return GITHUB_COM
    web_base = f"https://{host}" + (f":{port}" if port else "")
    return Endpoint(api_base=f"{web_base}/api/v3", web_base=web_base)


def host(endpoint: Endpoint) -> str:
    return endpoint.web_base.removeprefix("https://")


def account_label(account: GitHubAccount) -> str:
    return f"{account.login} · {host(account.endpoint)}"


def direction(reason: Reason) -> Direction:
    return Direction.OUTBOUND if reason == Reason.AUTHORED else Direction.INBOUND


def merge(found: Iterable[PullRequest]) -> list[PullRequest]:
    """One entry per pull request, most recently updated first. When a pull
    request matches several queries, the first reason found wins: a review
    request outranks an assignment, which outranks authorship."""
    by_id: dict[int, PullRequest] = {}
    for pull in found:
        by_id.setdefault(pull.pr_id, pull)
    return sorted(by_id.values(), key=lambda pull: (pull.updated, -pull.pr_id), reverse=True)


def topic(pull: PullRequest) -> Topic:
    """One topic per pull request, with the pull request as its one item."""
    item = Item(
        key=str(pull.pr_id),
        direction=direction(pull.reason),
        author=pull.author or None,
        url=pull.url,
        date=pull.updated,
        # SilentDesk only reads GitHub.
        deletable=False,
    )
    return Topic(
        key=str(pull.pr_id), title=pull.title.strip() or f"{pull.repo}#{pull.number}", items=[item], deletable=False
    )
