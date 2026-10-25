"""Pull requests and accounts, as far as SilentDesk needs them. Descriptions,
diffs and comments are never fetched."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Reason(enum.StrEnum):
    """Why a pull request is in the queue, strongest first."""

    REVIEW_REQUESTED = "reviewRequested"
    ASSIGNED = "assigned"
    AUTHORED = "authored"


@dataclass(frozen=True)
class Endpoint:
    # Such as https://api.github.com, or https://github.acme.com/api/v3.
    api_base: str
    # Such as https://github.com.
    web_base: str


@dataclass(frozen=True)
class PullRequest:
    pr_id: int
    # owner/name
    repo: str
    number: int
    title: str
    reason: Reason
    # The author's login.
    author: str
    draft: bool
    url: str
    # RFC 3339: last updated.
    updated: str


@dataclass(frozen=True)
class GitHubAccount:
    login: str
    # The display name, or the login when the user has none.
    name: str
    endpoint: Endpoint
