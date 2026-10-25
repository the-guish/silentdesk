from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.jira import Credential, Endpoint, Issue, JiraUser


class JiraApi(ABC):
    """Jira's REST API, read-only."""

    @abstractmethod
    async def myself(self, endpoint: Endpoint, credential: Credential) -> JiraUser:
        """The credential's user. Raises AuthError when Jira rejects it."""

    @abstractmethod
    async def cloud_id(self, site_base: str) -> str | None:
        """A Jira Cloud site's cloud ID, for Atlassian's gateway; None when
        the site does not say."""

    @abstractmethod
    async def open_issues(self, endpoint: Endpoint, credential: Credential, count: int) -> list[Issue]:
        """The `count` most recently updated open issues assigned to or
        reported by the user."""
