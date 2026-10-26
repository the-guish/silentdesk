"""Rules about Jira: sites, the search, dates and topics.
See docs/specs/integrations/jira/jira.md."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from ....contract import AuthError, Direction, Item, StatusCategory, Topic, TopicStatus
from ..domain.jira import Issue, JiraAccount

SERVICE = "jira"
# The most recently updated open issues kept.
SYNC_COUNT = 10


def normalize_site(text: str) -> str:
    """Accepts acme.atlassian.net, https://acme.atlassian.net/ or a Data
    Center address with a path, and returns https://host[:port][/path].
    Plain http is refused: tokens never travel unencrypted."""
    text = text.strip()
    url = urlsplit(text if "://" in text else f"https://{text}")
    if url.scheme != "https":
        raise AuthError(SERVICE, "The Jira site must use https://.")
    try:
        host, port = url.hostname, url.port
    except ValueError:
        host = port = None
    if not host or url.username or url.password:
        raise AuthError(SERVICE, "The Jira site address is not valid.")
    return f"https://{host}" + (f":{port}" if port else "") + url.path.rstrip("/")


def is_cloud_site(site: str) -> bool:
    return (urlsplit(site).hostname or "").endswith(".atlassian.net")


def account_label(account: JiraAccount) -> str:
    return f"{account.user_name} · {account.endpoint.site.removeprefix('https://')}"


def to_rfc3339(text: str | None) -> str:
    """Jira writes dates like 2026-10-23T10:00:00.000+0200. Returns RFC 3339
    in UTC, or an empty string for anything else."""
    try:
        moment = datetime.fromisoformat(text or "")
    except ValueError:
        return ""
    if moment.tzinfo is None:
        return ""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def topic(issue: Issue, account: JiraAccount) -> Topic:
    """One topic per issue, with the issue as its one item: inbound when it
    is assigned to the user, outbound when the user is waiting on it."""
    assigned_to_me = issue.assignee is not None and issue.assignee.id == account.user_id
    item = Item(
        key=issue.key,
        direction=Direction.INBOUND if assigned_to_me else Direction.OUTBOUND,
        author=issue.reporter.name if issue.reporter and issue.reporter.name else None,
        url=f"{account.endpoint.site}/browse/{issue.key}",
        date=to_rfc3339(issue.updated),
        # SilentDesk only reads Jira.
        deletable=False,
    )
    return Topic(
        key=issue.issue_id,
        title=issue.summary.strip() or issue.key,
        items=[item],
        deletable=False,
        status=status(issue.status, issue.status_category),
    )


# Jira's status categories, by statusCategory.key. See
# docs/specs/topic-status.md.
CATEGORIES = {"new": StatusCategory.NEW, "indeterminate": StatusCategory.IN_PROGRESS, "done": StatusCategory.DONE}


def status(name: str, category: str | None) -> TopicStatus | None:
    """The issue's status, or None when Jira gave it no name."""
    if not name.strip():
        return None
    return TopicStatus(name.strip(), CATEGORIES.get(category or ""))
