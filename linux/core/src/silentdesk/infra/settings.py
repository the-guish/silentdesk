"""Settings for one run of the core."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Where the database lives, such as ~/.local/share/silentdesk.
    data_dir: Path
    # A fixed clock in RFC 3339, for repeatable tests. None uses the system clock.
    now: str | None = None
    # A base URL per service, such as {"gmail": "http://127.0.0.1:8000"}, so
    # tests can point the core at a fake server.
    base_urls: Mapping[str, str] = field(default_factory=dict)
    google_client_id: str | None = None
    google_client_secret: str | None = None

    @classmethod
    def from_environment(cls) -> Settings:
        """Reads the XDG data folder and the SILENTDESK_* variables."""
        raise NotImplementedError
