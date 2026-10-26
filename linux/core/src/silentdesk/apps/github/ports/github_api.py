from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from ..domain.github import PullRequest, Reason


@dataclass(frozen=True)
class Me:
    login: str
    # None when the user has not set a display name.
    name: str | None


@dataclass(frozen=True)
class Found:
    """The pull requests the searches found. Not complete when GitHub could
    not read some of them, such as for a repository behind SAML."""

    pulls: list[PullRequest]
    complete: bool


class GitHubApi(ABC):
    """GitHub's REST and GraphQL APIs, read-only, with a personal access
    token."""

    @abstractmethod
    async def me(self, api_base: str, token: str) -> Me:
        """The token's user. Raises AuthError when GitHub rejects the token."""

    @abstractmethod
    async def open_pull_requests(self, graphql_url: str, token: str, queries: Sequence[tuple[str, Reason]]) -> Found:
        """The pull requests each search query finds, with its reason, in one
        GraphQL request to `graphql_url`."""
