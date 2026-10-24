from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Grant:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    # RFC 3339.
    expires_at: str
    email: str | None


class Authorization(ABC):
    """Google's OAuth: sign-in through the browser, then token refresh."""

    @abstractmethod
    async def sign_in(self, scopes: Sequence[str]) -> Grant:
        """Opens Google's sign-in page and waits for the user to finish."""

    @abstractmethod
    async def refresh(self, refresh_token: str) -> Grant: ...

    @abstractmethod
    async def revoke(self, token: str) -> None: ...
