"""Settings, from the environment or given directly."""

from __future__ import annotations

import os
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
        slack_client_id: str | None = None,
        slack_redirect_port: int = 47615,
        test_keyring: Path | None = None,
        test_base_url: str | None = None,
        test_browser: bool = False,
    ) -> None:
        self._data_dir = data_dir
        self._now = now
        # A base URL per service, such as {"gmail": "http://127.0.0.1:8000"}.
        self._base_urls = dict(base_urls or {})
        self._google_client_id = google_client_id
        self._google_client_secret = google_client_secret
        self._slack_client_id = slack_client_id
        self._slack_redirect_port = slack_redirect_port
        # For tests only, see spec/cli.md: a file that replaces the OS
        # credential store, and a fake server that replaces every service.
        self.test_keyring = test_keyring
        self.test_base_url = test_base_url.rstrip("/") if test_base_url else None
        # Sign-in pages are fetched and their redirects followed, instead of
        # opening a browser.
        self.test_browser = test_browser

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] = os.environ) -> LocalSettings:
        """The XDG data folder and the SILENTDESK_* variables in spec/cli.md.
        Empty variables count as unset."""

        def variable(name: str) -> str | None:
            return environ.get(name) or None

        data_home = variable("XDG_DATA_HOME") or str(Path(environ.get("HOME") or Path.home()) / ".local" / "share")
        test_keyring = variable("SILENTDESK_TEST_KEYRING")
        return cls(
            data_dir=Path(data_home) / "silentdesk",
            now=variable("SILENTDESK_TEST_NOW"),
            google_client_id=variable("SILENTDESK_GOOGLE_CLIENT_ID"),
            google_client_secret=variable("SILENTDESK_GOOGLE_CLIENT_SECRET"),
            slack_client_id=variable("SILENTDESK_SLACK_CLIENT_ID"),
            slack_redirect_port=_port(variable("SILENTDESK_SLACK_REDIRECT_PORT")),
            test_keyring=Path(test_keyring) if test_keyring else None,
            test_base_url=variable("SILENTDESK_TEST_BASE_URL"),
            test_browser=variable("SILENTDESK_TEST_BROWSER") == "follow",
        )

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def now(self) -> str | None:
        return self._now

    def base_url(self, service: str, default: str) -> str:
        if service in self._base_urls:
            return self._base_urls[service]
        return f"{self.test_base_url}/{service}" if self.test_base_url else default

    @property
    def google_client_id(self) -> str | None:
        return self._google_client_id

    @property
    def google_client_secret(self) -> str | None:
        return self._google_client_secret

    @property
    def slack_client_id(self) -> str | None:
        return self._slack_client_id

    @property
    def slack_redirect_port(self) -> int:
        return self._slack_redirect_port


def _port(text: str | None) -> int:
    """A port number; Slack's default when unset or not a valid port."""
    return int(text) if text and text.isdigit() and 0 < int(text) <= 0xFFFF else 47615
