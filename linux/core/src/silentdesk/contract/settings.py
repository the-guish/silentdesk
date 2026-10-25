"""Settings for one run of the core."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Settings(ABC):
    @property
    @abstractmethod
    def data_dir(self) -> Path:
        """Where the database lives, such as ~/.local/share/silentdesk."""

    @property
    @abstractmethod
    def now(self) -> str | None:
        """A fixed time in RFC 3339, for repeatable tests. None uses the system clock."""

    @abstractmethod
    def base_url(self, service: str, default: str) -> str:
        """The service's API address: `default`, unless tests point the core at a fake server."""

    @property
    @abstractmethod
    def google_client_id(self) -> str | None: ...

    @property
    @abstractmethod
    def google_client_secret(self) -> str | None: ...

    @property
    @abstractmethod
    def slack_client_id(self) -> str | None: ...

    @property
    @abstractmethod
    def slack_redirect_port(self) -> int:
        """Slack matches redirect URLs exactly, so the sign-in port is fixed."""
