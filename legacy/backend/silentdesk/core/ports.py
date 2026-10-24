"""What the application needs from the outside world. The Rust adapters in
`silentdesk.adapters.rust` implement these over IPC; tests use in-memory
fakes (`tests/fakes.py`).

The backend has no persistence of its own: data goes through `Store` and
secrets through `Secrets`, both kept by Rust.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from .model import VaultData

T = TypeVar("T")


class Store(Protocol):
    """The local data, kept and encrypted by Rust."""

    async def read(self) -> VaultData: ...

    async def update(self, change: Callable[[VaultData], T]) -> T:
        """Applies `change` to the current data and saves the result.
        Returns what `change` returns. `change` may run more than once if
        another writer got in first, so it must not have side effects."""
        ...


class Secrets(Protocol):
    """Tokens, kept by Rust in the OS credential store. Rust hands them over
    at startup; they live only in memory here."""

    def get(self, name: str) -> str | None: ...

    async def set(self, name: str, value: str) -> None: ...

    async def delete(self, name: str) -> None: ...


class Browser(Protocol):
    async def open(self, url: str) -> None:
        """Opens `url` in the system browser, for sign-in."""
        ...


class Events(Protocol):
    def emit(self, event: str, payload: Any) -> None:
        """Sends an event to the UI. Fire and forget."""
        ...


@dataclass(frozen=True)
class Config:
    """App registrations, from the environment or baked in at build time.
    `None` when unset."""

    google_client_id: str | None = None
    google_client_secret: str | None = None
    slack_client_id: str | None = None
    slack_redirect_port: str | None = None


@dataclass
class Host:
    """Everything a source needs, wired once at startup."""

    store: Store
    secrets: Secrets
    browser: Browser
    events: Events
    config: Config
