"""The GitHub source: what the UI calls as `github.status`,
`github.connect`, `github.sync` and `github.disconnect`."""

from __future__ import annotations

from typing import Any

from ...adapters import rest
from ...core import errors
from ...core.model import GitHubAccount, VaultData
from ...core.secret_names import GITHUB_TOKEN
from ...core.topics import now_rfc3339, topic_views
from ..base import ServiceStatus, Source
from . import api, domain

SERVICE = "GitHub"


class GitHubSource(Source):
    name = "github"

    def _load_token(self) -> str | None:
        return self.host.secrets.get(GITHUB_TOKEN)

    async def status(self) -> ServiceStatus:
        stored = (await self.host.store.read()).github_account
        account = f"{stored.login} · {api.host(stored.endpoint)}" if stored else None
        connected = account is not None and self._load_token() is not None
        # GitHub needs no app registration: the user brings a token.
        return ServiceStatus(configured=True, connected=connected, account=account)

    async def connect(self, params: dict[str, Any]) -> ServiceStatus:
        """Checks the token and stores it in the OS keychain. `server` is
        empty for github.com, or a GitHub Enterprise Server host. Switching
        to a different user or server drops the old account's local data."""
        endpoint = api.endpoint_for_server(rest.arg(params, "server", "github.connect", required=False))
        token = rest.arg(params, "token", "github.connect").strip()
        if not token:
            raise errors.Auth("enter a personal access token.")
        me = await api.connect(self.http, endpoint, token)
        await self.host.secrets.set(GITHUB_TOKEN, token)

        def change(data: VaultData) -> None:
            a = data.github_account
            same_account = a is not None and a.login == me.login and a.endpoint == endpoint
            if not same_account:
                domain.clear(data)
            data.github_account = GitHubAccount(endpoint=endpoint, login=me.login, name=me.name)

        await self.host.store.update(change)
        return await self.status()

    async def sync(self) -> list[dict[str, Any]]:
        """Pulls the open pull requests that involve the user and maps each
        one to a topic."""
        account = (await self.host.store.read()).github_account
        if account is None:
            raise errors.NotConnected(SERVICE)
        token = self._load_token()
        if token is None:
            raise errors.NotConnected(SERVICE)
        try:
            latest = await api.open_pull_requests(self.http, account.endpoint, token)
        except errors.Reauthorize:
            # Expired or revoked token. Forget it, keep the topics.
            await self.host.secrets.delete(GITHUB_TOKEN)
            raise
        now = now_rfc3339()

        def change(data: VaultData) -> list[dict[str, Any]]:
            domain.apply_sync(data, latest, now)
            return topic_views(data)

        return await self.host.store.update(change)

    async def disconnect(self) -> ServiceStatus:
        """Deletes the token and all local GitHub data. The user revokes the
        token itself in their GitHub settings."""
        await self.host.secrets.delete(GITHUB_TOKEN)
        await self.host.store.update(domain.clear)
        return await self.status()
