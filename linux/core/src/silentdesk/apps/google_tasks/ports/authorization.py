from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..domain.tasks import Grant


class Authorization(ABC):
    """Google sign-in: through the browser, then token refresh."""

    @property
    @abstractmethod
    def configured(self) -> bool:
        """Whether there is a client ID to sign in with."""

    @abstractmethod
    async def sign_in(self, scopes: Sequence[str], required: Sequence[str]) -> Grant:
        """Opens Google's sign-in page and waits for the user. Raises
        AuthError unless every `required` scope is granted, with a refresh
        token."""

    @abstractmethod
    async def access_token(self, refresh_token: str) -> str:
        """A fresh access token. Raises AuthError when the grant is gone."""

    @abstractmethod
    async def revoke(self, refresh_token: str) -> None:
        """Ends the grant at Google. Best effort."""
