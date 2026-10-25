from __future__ import annotations

from collections.abc import Callable, Mapping

from ....contract import AuthError, Connector, Message, RemoteError, ServiceStatus, SyncResult, Unsupported
from ..core import jira
from ..domain.jira import Credential, Endpoint, Flavor, JiraAccount, JiraUser
from ..ports.credentials import Credentials
from ..ports.jira_api import JiraApi
from ..ports.state_store import StateStore


class Jira(Connector):
    """The most recently updated open issues assigned to or reported by the
    user. Connects with a token: an email and API token for Jira Cloud, or a
    personal access token for Jira Data Center."""

    def __init__(
        self,
        api: JiraApi,
        credentials: Credentials,
        state: StateStore,
        site_base: Callable[[str], str],
        gateway_base: Callable[[], str],
    ) -> None:
        self.api = api
        self.credentials = credentials
        self.state = state
        # Where to reach a site, and Atlassian's gateway: their real
        # addresses, or a test server.
        self.site_base = site_base
        self.gateway_base = gateway_base

    @property
    def service(self) -> str:
        return jira.SERVICE

    async def status(self) -> ServiceStatus:
        account = await self.state.load()
        connected = account is not None and self.credentials.load() is not None
        # Jira needs no app registration: the user brings a token.
        return ServiceStatus(
            self.service,
            configured=True,
            connected=connected,
            account=jira.account_label(account) if connected else None,
        )

    async def connect(self, params: Mapping[str, str]) -> ServiceStatus:
        """Checks the token against the site, then keeps it. `email` is set
        for Jira Cloud and empty for Data Center. Nothing is stored on failure."""
        site = jira.normalize_site(params.get("site") or "")
        token = (params.get("token") or "").strip()
        if not token:
            raise AuthError(self.service, "Enter an API token.")
        credential = Credential((params.get("email") or "").strip() or None, token)
        endpoint, me = await self._find_endpoint(site, credential)
        self.credentials.save(credential)
        await self.state.save(JiraAccount(me.id or "", me.name, endpoint))
        return await self.status()

    async def _find_endpoint(self, site: str, credential: Credential) -> tuple[Endpoint, JiraUser]:
        """The site's own API first. Atlassian accepts a scoped Cloud token
        only through its gateway, so on 401 from a Cloud site the site's
        cloud ID is looked up and the gateway is tried."""
        rejected = AuthError(self.service, "Jira rejected the token. Check the site, email and API token.")
        direct = Endpoint(site, self.site_base(site), credential.flavor)
        try:
            return direct, await self._me(direct, credential)
        except AuthError:
            if credential.flavor != Flavor.CLOUD or not jira.is_cloud_site(site):
                raise rejected from None
        except RemoteError as error:
            if error.status == 404:
                raise AuthError(self.service, f"No Jira was found at {site}. Check the site address.") from error
            raise
        cloud_id = await self.api.cloud_id(self.site_base(site))
        if cloud_id is None:
            raise rejected
        gateway = Endpoint(site, f"{self.gateway_base()}/{cloud_id}", credential.flavor)
        try:
            return gateway, await self._me(gateway, credential)
        except AuthError:
            raise rejected from None

    async def _me(self, endpoint: Endpoint, credential: Credential) -> JiraUser:
        me = await self.api.myself(endpoint, credential)
        if me.id is None:
            raise AuthError(self.service, "Jira did not identify the user.")
        return me

    async def disconnect(self) -> ServiceStatus:
        """Forgets the token and the account. Jira has no API to revoke an API
        token: the user revokes it in their Atlassian or Jira profile."""
        self.credentials.delete()
        await self.state.clear()
        return await self.status()

    async def sync(self) -> SyncResult:
        account = await self.state.load()
        credential = self.credentials.load()
        if account is None or credential is None:
            raise AuthError(self.service, "Jira is not connected.")
        try:
            issues = await self.api.open_issues(account.endpoint, credential, jira.SYNC_COUNT)
        except AuthError as error:
            # Expired or revoked: forget the token, keep the topics.
            self.credentials.delete()
            raise AuthError(self.service, "Jira rejected the token. Connect again.") from error
        return SyncResult(
            [jira.topic(issue, account) for issue in issues[: jira.SYNC_COUNT]], removed=[], complete=True
        )

    async def reply(self, topic_key: str, body: str) -> None:
        raise Unsupported(self.service, "SilentDesk cannot comment on a Jira issue yet.")

    async def history(self, topic_key: str) -> list[Message]:
        raise Unsupported(self.service, "Jira has no conversation to show.")

    async def delete_topic(self, topic_key: str) -> None:
        raise Unsupported(self.service, "SilentDesk cannot delete a Jira issue.")

    async def delete_item(self, topic_key: str, item_key: str) -> None:
        raise Unsupported(self.service, "SilentDesk cannot delete a Jira issue.")
