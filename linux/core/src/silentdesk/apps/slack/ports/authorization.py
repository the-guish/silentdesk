from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.slack import Credential


class Authorization(ABC):
    """Slack sign-in: OAuth v2 with PKCE through the browser, for a user token."""

    @property
    @abstractmethod
    def configured(self) -> bool:
        """Whether there is a Slack client ID to sign in with."""

    @abstractmethod
    async def sign_in(self) -> Credential:
        """Raises AuthError unless every user scope is granted."""

    @abstractmethod
    async def refresh(self, credential: Credential) -> Credential:
        """A new access token. Raises AuthError when the grant is gone."""

    @abstractmethod
    async def revoke(self, access_token: str) -> None:
        """Ends the token at Slack. Best effort."""
