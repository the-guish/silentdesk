from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.slack import Match, SlackAccount


class SlackApi(ABC):
    """The Slack Web API, read-only, with a user token."""

    @abstractmethod
    async def identity(self, token: str) -> SlackAccount: ...

    @abstractmethod
    async def search(self, token: str, query: str, count: int) -> list[Match]:
        """Messages matching a search, newest first."""

    @abstractmethod
    async def user_name(self, token: str, user_id: str) -> str:
        """A user's display name, or empty when it cannot be read."""
