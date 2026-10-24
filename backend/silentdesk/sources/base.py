"""What every source (Gmail, Slack, Jira, GitHub, Google Tasks) offers the
app. A source is an application service: it uses the ports in `Host` and
its own API client, and holds no state beyond the in-memory op lock."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from ..core.ports import Host

# A method the UI can call, taking the call's JSON params.
Method = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass
class ServiceStatus:
    """What the UI needs to know about one connected service."""

    # The app has the client ID it needs to sign in.
    configured: bool
    # A token is stored and an account is known.
    connected: bool
    # The account as shown to the user.
    account: str | None


class Source:
    """Base for every source. Subclasses set `name` (the method prefix and
    the service id the UI uses) and implement the four operations."""

    name: str

    def __init__(self, host: Host, http: httpx.AsyncClient):
        self.host = host
        # From `adapters.http.make_client`; tests pass a mock transport.
        self.http = http
        # One operation (connect, sync, disconnect, an action) per source at
        # a time. User actions wait for it; automatic syncs skip a source
        # whose lock is taken.
        self.op = asyncio.Lock()

    async def status(self) -> ServiceStatus:
        raise NotImplementedError

    async def connect(self, params: dict[str, Any]) -> ServiceStatus:
        raise NotImplementedError

    async def sync(self) -> list[dict[str, Any]]:
        """Syncs without taking `op`; callers hold it. Returns the topic
        views."""
        raise NotImplementedError

    async def disconnect(self) -> ServiceStatus:
        raise NotImplementedError

    def actions(self) -> dict[str, Method]:
        """Extra methods beyond the four, e.g. Gmail's `trash`. Each takes
        `op` itself."""
        return {}

    def methods(self) -> dict[str, Method]:
        """Every method this source answers, keyed `<name>.<method>`."""

        async def status(_: dict[str, Any]) -> ServiceStatus:
            return await self.status()

        async def connect(params: dict[str, Any]) -> ServiceStatus:
            async with self.op:
                return await self.connect(params)

        async def sync(_: dict[str, Any]) -> list[dict[str, Any]]:
            async with self.op:
                return await self.sync()

        async def disconnect(_: dict[str, Any]) -> ServiceStatus:
            async with self.op:
                return await self.disconnect()

        table: dict[str, Method] = {
            "status": status,
            "connect": connect,
            "sync": sync,
            "disconnect": disconnect,
            **self.actions(),
        }
        return {f"{self.name}.{k}": v for k, v in table.items()}
