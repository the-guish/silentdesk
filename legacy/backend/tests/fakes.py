"""In-memory stand-ins for the ports Rust implements, for tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from silentdesk.adapters.http import make_client
from silentdesk.core.model import VaultData, from_json, to_json
from silentdesk.core.ports import Config, Host

T = TypeVar("T")


class MemoryStore:
    """Keeps the data as JSON, like Rust does, so every write goes through
    the codec and a test fails if a source stores something the schema
    cannot hold."""

    def __init__(self, data: VaultData | None = None):
        self.json = json.dumps(to_json(data or VaultData()))
        self.writes = 0

    async def read(self) -> VaultData:
        return from_json(VaultData, json.loads(self.json))

    async def update(self, change: Callable[[VaultData], T]) -> T:
        data = await self.read()
        out = change(data)
        encoded = to_json(data)
        assert to_json(from_json(VaultData, encoded)) == encoded, "write does not match the schema"
        self.json = json.dumps(encoded)
        self.writes += 1
        return out

    def data(self) -> VaultData:
        return from_json(VaultData, json.loads(self.json))


class MemorySecrets:
    def __init__(self, values: dict[str, str] | None = None):
        self.values = dict(values or {})

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def set(self, name: str, value: str) -> None:
        self.values[name] = value

    async def delete(self, name: str) -> None:
        self.values.pop(name, None)


class FakeBrowser:
    """Records opened URLs. `on_open`, if set, runs with each URL, e.g. to
    play the provider's redirect back to the loopback listener."""

    def __init__(self, on_open: Callable[[str], Any] | None = None):
        self.opened: list[str] = []
        self.on_open = on_open

    async def open(self, url: str) -> None:
        self.opened.append(url)
        if self.on_open is not None:
            result = self.on_open(url)
            if hasattr(result, "__await__"):
                await result


class RecordingEvents:
    def __init__(self):
        self.events: list[tuple[str, Any]] = []

    def emit(self, event: str, payload: Any) -> None:
        self.events.append((event, payload))


def make_host(
    data: VaultData | None = None,
    secrets: dict[str, str] | None = None,
    config: Config | None = None,
    browser: FakeBrowser | None = None,
) -> Host:
    return Host(
        store=MemoryStore(data),
        secrets=MemorySecrets(secrets),
        browser=browser or FakeBrowser(),
        events=RecordingEvents(),
        config=config or Config(),
    )


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """An HTTP client whose requests go to `handler` instead of the network."""
    return make_client(httpx.MockTransport(handler))
