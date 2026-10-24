"""The Jira source: what the UI calls as `jira.status`, `jira.connect`,
`jira.sync` and `jira.disconnect`."""

from __future__ import annotations

from typing import Any

from ...adapters import rest
from ...core import errors
from ...core.model import JiraAccount, VaultData
from ...core.secret_names import JIRA_CREDENTIAL
from ...core.topics import now_rfc3339, topic_views
from ..base import ServiceStatus, Source
from . import api, domain

SERVICE = "Jira"


def site_label(site: str) -> str:
    while site.startswith("https://"):
        site = site[len("https://") :]
    return site


class JiraSource(Source):
    name = "jira"

    def _load_credential(self) -> api.Credential | None:
        stored = self.host.secrets.get(JIRA_CREDENTIAL)
        return api.Credential.from_secret(stored) if stored is not None else None

    async def status(self) -> ServiceStatus:
        stored = (await self.host.store.read()).jira_account
        account = f"{stored.user_name} · {site_label(stored.endpoint.site)}" if stored else None
        connected = account is not None and self._load_credential() is not None
        # Jira needs no app registration: the user brings a token.
        return ServiceStatus(configured=True, connected=connected, account=account)

    async def connect(self, params: dict[str, Any]) -> ServiceStatus:
        """Checks the token against the site and stores it in the OS
        keychain. `email` is set for Jira Cloud and empty for a Data Center
        personal access token. Switching to a different user or site drops
        the old account's local data."""
        site = api.normalize_site(rest.arg(params, "site", "jira.connect"))
        email = rest.arg(params, "email", "jira.connect", required=False)
        token = rest.arg(params, "token", "jira.connect").strip()
        if not token:
            raise errors.Auth("enter an API token.")
        email = email.strip() if email is not None else None
        credential = api.Credential(email=email or None, token=token)
        endpoint, me = await api.connect(self.http, site, credential)

        await self.host.secrets.set(JIRA_CREDENTIAL, credential.to_secret())

        def change(data: VaultData) -> None:
            a = data.jira_account
            same_account = a is not None and a.user_id == me.id and a.endpoint.site == endpoint.site
            if not same_account:
                domain.clear(data)
            data.jira_account = JiraAccount(endpoint=endpoint, user_id=me.id, user_name=me.name)

        await self.host.store.update(change)
        return await self.status()

    async def sync(self) -> list[dict[str, Any]]:
        """Pulls the most recently updated open issues and maps each one to
        a topic."""
        account = (await self.host.store.read()).jira_account
        if account is None:
            raise errors.NotConnected(SERVICE)
        credential = self._load_credential()
        if credential is None:
            raise errors.NotConnected(SERVICE)
        try:
            latest = await api.open_issues(self.http, credential, account.endpoint, account.user_id, domain.SYNC_COUNT)
        except errors.Reauthorize:
            # Expired or revoked token. Forget it, keep the topics.
            await self.host.secrets.delete(JIRA_CREDENTIAL)
            raise
        now = now_rfc3339()

        def change(data: VaultData) -> list[dict[str, Any]]:
            domain.apply_sync(data, latest, now)
            return topic_views(data)

        return await self.host.store.update(change)

    async def disconnect(self) -> ServiceStatus:
        """Deletes the token and all local Jira data. API tokens cannot be
        revoked through the API; the user revokes them in their Atlassian or
        Jira profile."""
        await self.host.secrets.delete(JIRA_CREDENTIAL)
        await self.host.store.update(domain.clear)
        return await self.status()
