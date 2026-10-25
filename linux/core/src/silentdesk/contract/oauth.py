"""OAuth 2.0 sign-in through the user's browser, for any provider: the
authorization code flow with PKCE (RFC 7636) and a loopback redirect (RFC
8252). The browser does the sign-in, so SilentDesk never sees the user's
password, and SSO or MFA work as usual."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OAuthClient:
    """An OAuth client an organization registered with a provider."""

    # The service it signs in to, named in errors.
    service: str
    authorize_url: str
    token_url: str
    client_id: str
    # Desktop clients may get a secret that is not confidential; PKCE
    # protects the flow either way.
    client_secret: str | None = field(default=None, repr=False)
    # More authorization parameters, such as {"access_type": "offline"}.
    extra: Mapping[str, str] = field(default_factory=dict)
    # Where the provider redirects: any free loopback port at "/", or, for
    # providers that match the registered URL exactly, a fixed port and path.
    port: int | None = None
    path: str = "/"
    # How scopes are sent: Slack, for one, wants user_scope=a,b.
    scope_param: str = "scope"
    scope_separator: str = " "


@dataclass(frozen=True)
class Tokens:
    access_token: str | None = field(repr=False)
    refresh_token: str | None = field(repr=False)
    scopes: tuple[str, ...]
    # The whole token response, for providers that add their own fields.
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)


class OAuth(ABC):
    @abstractmethod
    async def sign_in(self, client: OAuthClient, scopes: Sequence[str]) -> Tokens:
        """Opens the provider's sign-in page, waits for it to redirect back,
        and exchanges the code. Raises AuthError when the user declines, the
        sign-in times out, or the provider refuses."""

    @abstractmethod
    async def refresh(self, client: OAuthClient, refresh_token: str) -> Tokens:
        """A new access token. Raises AuthError when the grant is gone."""

    @abstractmethod
    async def revoke(self, url: str, token: str) -> None:
        """Asks the provider to end the grant. Best effort: it never raises."""
