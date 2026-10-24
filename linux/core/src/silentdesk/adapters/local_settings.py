"""Settings, from the environment or given directly."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..contract import Settings


class LocalSettings(Settings):
    def __init__(
        self,
        data_dir: Path,
        now: str | None = None,
        base_urls: Mapping[str, str] | None = None,
        google_client_id: str | None = None,
        google_client_secret: str | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._now = now
        # A base URL per service, such as {"gmail": "http://127.0.0.1:8000"}.
        self._base_urls = dict(base_urls or {})
        self._google_client_id = google_client_id
        self._google_client_secret = google_client_secret

    @classmethod
    def from_environment(cls) -> LocalSettings:
        """Reads the XDG data folder and the SILENTDESK_* variables."""
        raise NotImplementedError

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def now(self) -> str | None:
        return self._now

    def base_url(self, service: str, default: str) -> str:
        return self._base_urls.get(service, default)

    @property
    def google_client_id(self) -> str | None:
        return self._google_client_id

    @property
    def google_client_secret(self) -> str | None:
        return self._google_client_secret
