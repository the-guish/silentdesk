"""Jira issues, sites and accounts, as far as SilentDesk needs them.
Descriptions and comments are never fetched."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Flavor(enum.StrEnum):
    # Jira Cloud: email and API token (HTTP Basic), REST API v3.
    CLOUD = "cloud"
    # Jira Data Center: personal access token (Bearer), REST API v2.
    DATA_CENTER = "dataCenter"


@dataclass(frozen=True)
class Credential:
    """With an email, a Jira Cloud API token; without, a Data Center
    personal access token."""

    email: str | None
    token: str = field(repr=False)

    @property
    def flavor(self) -> Flavor:
        return Flavor.CLOUD if self.email else Flavor.DATA_CENTER


@dataclass(frozen=True)
class Endpoint:
    # Such as https://acme.atlassian.net: issues open from here.
    site: str
    # Where the REST API is: the site, or Atlassian's gateway for scoped tokens.
    api_base: str
    flavor: Flavor


@dataclass(frozen=True)
class JiraAccount:
    # The Cloud account ID, or the Data Center user key.
    user_id: str
    user_name: str
    endpoint: Endpoint


@dataclass(frozen=True)
class JiraUser:
    id: str | None
    name: str


@dataclass(frozen=True)
class Issue:
    issue_id: str
    # Such as PAY-412.
    key: str
    summary: str
    status: str
    project: str
    assignee: JiraUser | None
    reporter: JiraUser | None
    # As Jira writes it, such as 2026-10-23T10:00:00.000+0200; None when absent.
    updated: str | None
