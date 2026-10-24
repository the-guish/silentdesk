"""SilentDesk's own data model, mirroring the schemas the Rust side defines
in `src-tauri/src/model.rs`. Rust owns persistence: it checks every write
against those schemas, so the two must stay in step. See
docs/specs/data-model.md and docs/specs/backend.md.

JSON uses camelCase keys, like the Rust side. Every field is always written,
`None` as `null`, because Rust rejects writes that do not match its schema
exactly.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from dataclasses import dataclass, field
from typing import Any


class Direction(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class Topic:
    """A unit of work the user can act on. Source items each belong to
    exactly one topic."""

    id: str
    title: str
    # RFC 3339.
    created_at: str


@dataclass
class GmailMessage:
    """A reference to one Gmail message, plus the headers needed to show it in
    a queue. Bodies are never fetched or stored. Inbox syncs keep the subject
    only, so `from_` and `to` are empty for them."""

    message_id: str
    thread_id: str
    topic_id: str
    direction: Direction
    from_: str = field(metadata={"json": "from"})
    to: str
    subject: str
    # RFC 3339, from Gmail's internal date.
    date: str


@dataclass
class GmailAccount:
    email: str


@dataclass
class SlackMessage:
    """A reference to one Slack direct message. The message text is not kept:
    its first line becomes the topic title, and the permalink opens it."""

    channel_id: str
    ts: str
    topic_id: str
    direction: Direction
    author: str
    # Who the conversation is with: the other person, or "Group DM".
    counterpart: str
    permalink: str
    # RFC 3339, from the message timestamp.
    date: str


@dataclass
class SlackAccount:
    user_id: str
    user_name: str
    team_id: str
    team_name: str


class JiraFlavor(enum.StrEnum):
    CLOUD = "cloud"
    DATA_CENTER = "dataCenter"


@dataclass
class JiraEndpoint:
    """Where and how to call the Jira API, decided once at connect time."""

    # The site people browse, e.g. `https://acme.atlassian.net`.
    site: str
    # The site itself, or the Atlassian gateway for scoped Cloud tokens.
    api_base: str
    flavor: JiraFlavor


@dataclass
class JiraIssue:
    """A reference to one Jira issue. The description and comments are not
    kept: the summary becomes the topic title, and the URL opens the issue."""

    issue_id: str
    key: str
    topic_id: str
    # Inbound when assigned to the user, outbound when the user reported it
    # and someone else (or no one) has it.
    direction: Direction
    status: str
    project: str
    assignee: str
    reporter: str
    url: str
    # RFC 3339, when the issue was last updated.
    date: str


@dataclass
class JiraAccount:
    endpoint: JiraEndpoint
    user_id: str
    user_name: str


class PullRequestReason(enum.StrEnum):
    """Why a pull request is in the user's queue."""

    REVIEW_REQUESTED = "reviewRequested"
    ASSIGNED = "assigned"
    AUTHORED = "authored"


@dataclass
class GitHubEndpoint:
    # `https://api.github.com` or `https://<host>/api/v3`.
    api_base: str
    # `https://github.com` or `https://<host>`.
    web_base: str


@dataclass
class PullRequest:
    """A reference to one GitHub pull request. The description, diff and
    comments are not kept: the title becomes the topic title, and the URL
    opens the pull request."""

    pr_id: int
    # `owner/name`.
    repo: str
    number: int
    topic_id: str
    reason: PullRequestReason
    # Inbound when the user's review or work is asked for; outbound when the
    # user opened it.
    direction: Direction
    draft: bool
    author: str
    url: str
    # RFC 3339, when the pull request was last updated.
    date: str


@dataclass
class GitHubAccount:
    endpoint: GitHubEndpoint
    login: str
    name: str


@dataclass
class GoogleTask:
    """A reference to one open Google Task. Notes are not kept: the title
    becomes the topic title, and the URL opens the task in Google Tasks."""

    task_id: str
    list_id: str
    list_title: str
    topic_id: str
    # `YYYY-MM-DD`; Google keeps the day only.
    due: str | None
    # Gmail, Docs or Chat, when the task came from one of them.
    origin: str | None
    url: str
    # RFC 3339, when the task was last updated.
    date: str


@dataclass
class TasksAccount:
    email: str


@dataclass
class VaultData:
    """Everything SilentDesk stores locally. Rust encrypts it at rest."""

    topics: list[Topic] = field(default_factory=list)
    gmail_account: GmailAccount | None = None
    gmail_messages: list[GmailMessage] = field(default_factory=list)
    # Where the next Gmail sync starts listing changes from. `None` until a
    # full Inbox sync completes.
    gmail_history_id: str | None = None
    slack_account: SlackAccount | None = None
    slack_messages: list[SlackMessage] = field(default_factory=list)
    jira_account: JiraAccount | None = None
    jira_issues: list[JiraIssue] = field(default_factory=list)
    github_account: GitHubAccount | None = None
    pull_requests: list[PullRequest] = field(default_factory=list)
    tasks_account: TasksAccount | None = None
    google_tasks: list[GoogleTask] = field(default_factory=list)


# --- JSON codec -----------------------------------------------------------


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def json_name(f: dataclasses.Field) -> str:
    return f.metadata.get("json") or camel(f.name)


def to_json(value: Any) -> Any:
    """Converts model objects to JSON-ready values with camelCase keys."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {json_name(f): to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, list):
        return [to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    return value


def from_json[T](cls: type[T], data: Any) -> T:
    """Builds a model object from JSON. Missing keys take the field default;
    unknown keys are ignored."""
    return _decode(cls, data)


def _decode(tp: Any, data: Any) -> Any:
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if data is None:
            return None
        return _decode(args[0], data)
    if origin is list:
        (item,) = typing.get_args(tp)
        return [_decode(item, v) for v in data]
    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        kwargs = {}
        for f in dataclasses.fields(tp):
            key = json_name(f)
            if key in data:
                kwargs[f.name] = _decode(hints[f.name], data[key])
        return tp(**kwargs)
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return tp(data)
    return data
