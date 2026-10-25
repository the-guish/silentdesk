from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.github import PullRequest, Reason


@dataclass(frozen=True)
class Me:
    login: str
    # None when the user has not set a display name.
    name: str | None


class GitHubApi(ABC):
    """GitHub's REST API, read-only, with a personal access token."""

    @abstractmethod
    async def me(self, api_base: str, token: str) -> Me:
        """The token's user. Raises AuthError when GitHub rejects the token."""

    @abstractmethod
    async def search(self, api_base: str, token: str, query: str, reason: Reason) -> list[PullRequest]:
        """Open pull requests matching one search query, given `reason`."""
