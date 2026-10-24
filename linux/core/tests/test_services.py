"""Settings from the environment, the keyrings, and each connector's status."""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path

from silentdesk import api
from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.local_settings import LocalSettings
from silentdesk.contract import ServiceStatus


def test_settings_come_from_xdg_and_silentdesk_variables(tmp_path):
    settings = LocalSettings.from_environment(
        {
            "HOME": "/home/ana",
            "XDG_DATA_HOME": str(tmp_path),
            "SILENTDESK_GOOGLE_CLIENT_ID": "client",
            "SILENTDESK_GOOGLE_CLIENT_SECRET": "",
            "SILENTDESK_TEST_KEYRING": str(tmp_path / "keyring.json"),
        }
    )
    assert settings.data_dir == tmp_path / "silentdesk"
    assert settings.google_client_id == "client"
    # Empty counts as unset.
    assert settings.google_client_secret is None
    assert settings.test_keyring == tmp_path / "keyring.json"


def test_settings_default_to_the_home_data_folder():
    settings = LocalSettings.from_environment({"HOME": "/home/ana"})
    assert settings.data_dir == Path("/home/ana/.local/share/silentdesk")
    assert settings.google_client_id is None
    assert settings.test_keyring is None


def test_file_keyring_keeps_entries_in_a_private_file(tmp_path):
    keyring = FileKeyring(tmp_path / "keys" / "keyring.json")
    assert keyring.get("gmail-refresh-token") is None

    keyring.set("gmail-refresh-token", "secret")
    keyring.set("database-key", "key")
    keyring.delete("database-key")
    keyring.delete("never-set")

    assert keyring.get("gmail-refresh-token") == "secret"
    assert keyring.get("database-key") is None
    assert stat.S_IMODE(keyring.path.stat().st_mode) == 0o600


def statuses(tmp_path, client_id: str | None = None) -> list[ServiceStatus]:
    settings = LocalSettings(tmp_path, google_client_id=client_id, test_keyring=tmp_path / "keyring.json")
    return asyncio.run(api.desk(settings).services())


def test_services_are_listed_by_name_and_need_a_client_id_to_be_configured(tmp_path):
    assert statuses(tmp_path) == [
        ServiceStatus("github", configured=True, connected=False, account=None),
        ServiceStatus("gmail", configured=False, connected=False, account=None),
        ServiceStatus("jira", configured=True, connected=False, account=None),
        ServiceStatus("tasks", configured=False, connected=False, account=None),
    ]
    assert all(status.configured for status in statuses(tmp_path, client_id="client"))
