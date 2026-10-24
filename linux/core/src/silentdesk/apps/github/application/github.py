from __future__ import annotations

from collections.abc import Callable, Mapping

from ....contract import AuthError, Connector, ServiceStatus, SyncResult, Unsupported
from ..core import github
from ..domain.github import Endpoint, GitHubAccount
from ..ports.credentials import Credentials
from ..ports.github_api import GitHubApi
from ..ports.state_store import StateStore


class GitHub(Connector):
    """Open pull requests that request the user's review, are assigned to the
    user, or were opened by the user. Connects with a personal access token,
    to github.com or a GitHub Enterprise Server."""

    def __init__(
        self,
        api: GitHubApi,
        credentials: Credentials,
        state: StateStore,
        api_base: Callable[[Endpoint], str],
    ) -> None:
        self.api = api
        self.credentials = credentials
        self.state = state
        # Where to reach an endpoint's API: its own address, or a test server.
        self.api_base = api_base

    @property
    def service(self) -> str:
        return github.SERVICE

    async def status(self) -> ServiceStatus:
        account = await self.state.load()
        connected = account is not None and self.credentials.token() is not None
        # GitHub needs no app registration: the user brings a token.
        return ServiceStatus(
            self.service,
            configured=True,
            connected=connected,
            account=github.account_label(account) if account and connected else None,
        )

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        """Checks the token, then keeps it. `server` is empty for github.com,
        or a GitHub Enterprise Server host. Nothing is stored on failure."""
        endpoint = github.endpoint_for_server(params.get("server"))
        token = (params.get("token") or "").strip()
        if not token:
            raise AuthError(self.service, "Enter a personal access token.")
        me = await self.api.me(self.api_base(endpoint), token)
        self.credentials.save_token(token)
        await self.state.save(GitHubAccount(me.login, me.name or me.login, endpoint))
        return await self.status()

    async def disconnect(self) -> ServiceStatus:
        """Forgets the token and the account. GitHub has no API to revoke a
        personal access token: the user deletes it in their GitHub settings."""
        self.credentials.delete_token()
        await self.state.clear()
        return await self.status()

    async def sync(self) -> SyncResult:
        account = await self.state.load()
        token = self.credentials.token()
        if account is None or token is None:
            raise AuthError(self.service, "GitHub is not connected.")
        found = []
        try:
            for query, reason in github.QUERIES:
                found += await self.api.search(self.api_base(account.endpoint), token, query, reason)
        except AuthError as error:
            # Expired or revoked: forget the token, keep the topics.
            self.credentials.delete_token()
            raise AuthError(self.service, "GitHub rejected the token. Connect again.") from error
        return SyncResult([github.topic(pull) for pull in github.merge(found)], removed=[], complete=True)

    async def reply(self, topic_key: str, body: str) -> None:
        raise Unsupported(self.service, "SilentDesk cannot reply to a pull request.")

    async def delete_topic(self, topic_key: str) -> None:
        raise Unsupported(self.service, "SilentDesk cannot delete a pull request.")
