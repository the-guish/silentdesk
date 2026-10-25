"""The Slack connector: its text rules, its sign-in and its syncs."""

from __future__ import annotations

import asyncio

import pytest

from silentdesk.adapters.file_keyring import FileKeyring
from silentdesk.adapters.sqlcipher_database import SqlcipherDatabase
from silentdesk.apps.slack.adapters.keyring_credentials import KeyringCredentials
from silentdesk.apps.slack.adapters.slack_authorization import SlackAuthorization
from silentdesk.apps.slack.adapters.sqlcipher_state_store import SqlcipherStateStore
from silentdesk.apps.slack.application.slack import Slack
from silentdesk.apps.slack.core import slack
from silentdesk.apps.slack.domain.slack import Credential, Match, SlackAccount
from silentdesk.apps.slack.ports.authorization import Authorization
from silentdesk.apps.slack.ports.slack_api import SlackApi
from silentdesk.contract import AuthError, Direction, OAuth, OAuthClient, Tokens


def test_slack_markup_becomes_plain_text():
    text = "Hi <@U1>, see <#C9|general> and <https://x.example|the doc> &amp; <!here> <@U2|bo>"
    assert slack.plain_text(text, {"U1": "Ana"}) == "Hi @Ana, see #general and the doc & @here @bo"
    assert slack.mention_ids("<@U2|bo> <@U1> <@U1>") == ["U1", "U2"]


def test_previews_are_cut_on_a_word_boundary():
    assert slack.preview("  one   two  ") == "one two"
    assert slack.preview("alpha beta gamma", limit=12) == "alpha beta…"


def match(ts: str, channel: str = "D1", user: str = "U2", im: bool = True, text: str = "Hello") -> Match:
    return Match(channel, "U2" if im else "mpdm-x", im, not im, user, None, text, ts, f"https://x.slack.com/p{ts}")


def test_only_direct_messages_are_kept_newest_first_without_repeats():
    channel_post = Match("C1", "general", False, False, "U2", None, "Hi", "5.0", "")
    picked = slack.select_recent(
        [match("1.0"), channel_post, match("3.0"), match("1.0"), match("2.0", "G1", im=False)], 2
    )
    assert [(m.channel_id, m.ts) for m in picked] == [("D1", "3.0"), ("G1", "2.0")]


def test_tokens_with_rotation_refresh_shortly_before_they_expire():
    assert slack.needs_refresh(Credential("a", "r", 1000), now=950)
    assert not slack.needs_refresh(Credential("a", "r", 1000), now=900)
    assert not slack.needs_refresh(Credential("a", None, None), now=10**10)


class FakeOAuth(OAuth):
    def __init__(self, raw: dict):
        self.raw = raw

    async def sign_in(self, client, scopes):
        return Tokens(None, None, (), self.raw)

    async def refresh(self, client, refresh_token):
        return Tokens(None, None, (), self.raw)

    async def revoke(self, url, token):
        pass


CLIENT = OAuthClient("slack", "a", "t", "client", port=47615, path="/slack/callback")
SCOPES = "search:read,users:read,im:history,mpim:history"


def test_sign_in_takes_the_user_token_and_needs_every_scope():
    granted = {
        "ok": True,
        "authed_user": {"access_token": "xoxp-1", "scope": SCOPES, "refresh_token": "xoxe-1", "expires_in": 43200},
    }
    credential = asyncio.run(SlackAuthorization(FakeOAuth(granted), CLIENT, "r").sign_in())
    assert (credential.access_token, credential.refresh_token) == ("xoxp-1", "xoxe-1")
    assert credential.expires_at is not None

    partial = {"ok": True, "authed_user": {"access_token": "xoxp-1", "scope": "search:read"}}
    with pytest.raises(AuthError, match="not fully granted"):
        asyncio.run(SlackAuthorization(FakeOAuth(partial), CLIENT, "r").sign_in())


@pytest.mark.parametrize(
    ("error", "match_text"),
    [
        ("bad_redirect_uri", "http://localhost:47615/slack/callback"),
        ("invalid_client_id", "PKCE"),
        ("invalid_code", "invalid_code"),
    ],
)
def test_slack_sign_in_errors_say_what_to_fix(error, match_text):
    with pytest.raises(AuthError, match=match_text):
        asyncio.run(SlackAuthorization(FakeOAuth({"ok": False, "error": error}), CLIENT, "r").sign_in())


def test_a_refresh_without_a_new_refresh_token_keeps_the_old_one():
    fresh = asyncio.run(
        SlackAuthorization(FakeOAuth({"ok": True, "access_token": "xoxp-2", "expires_in": 60}), CLIENT, "r").refresh(
            Credential("xoxp-1", "xoxe-1", 0)
        )
    )
    assert (fresh.access_token, fresh.refresh_token) == ("xoxp-2", "xoxe-1")


class FakeApi(SlackApi):
    def __init__(self, found: dict[str, list[Match]]):
        self.found, self.looked_up, self.entries = found, [], []

    async def identity(self, token):
        return SlackAccount("U0", "Ana", "T1", "Acme")

    async def search(self, token, query, count):
        return self.found.get(query, [])

    async def history(self, token, channel_id, count):
        return self.entries

    async def user_name(self, token, user_id):
        self.looked_up.append(user_id)
        return {"U2": "Bo", "U3": "Cy"}.get(user_id, "")


class FakeAuthorization(Authorization):
    @property
    def configured(self) -> bool:
        return True

    async def sign_in(self):
        return Credential("xoxp-1", None, None)

    async def refresh(self, credential):
        raise AuthError("slack", "Expired.")

    async def revoke(self, access_token):
        pass


def test_a_sync_makes_one_topic_per_conversation_with_names(tmp_path):
    keyring = FileKeyring(tmp_path / "keyring.json")
    api = FakeApi(
        {
            "to:me": [match("10.0", text="Ping <@U0>"), match("20.0", "G1", user="U3", im=False, text="Lunch?")],
            "from:<@U0>": [match("15.0", user="U0", text="Pong")],
        }
    )
    app = Slack(
        api,
        FakeAuthorization(),
        KeyringCredentials(keyring),
        SqlcipherStateStore(SqlcipherDatabase(tmp_path / "db", keyring)),
    )
    status = asyncio.run(app.connect({}))
    assert status.account == "Ana · Acme"

    topics = {t.key: t for t in asyncio.run(app.sync()).topics}

    assert topics["D1"].title == "Pong"
    assert [(i.key, i.direction, i.author) for i in topics["D1"].items] == [
        ("10.0", Direction.INBOUND, "Bo"),
        ("15.0", Direction.OUTBOUND, "someone"),
    ]
    assert topics["G1"].title == "Lunch?"
    # Each name is looked up once per sync.
    assert sorted(api.looked_up) == ["U0", "U2", "U3"]


def test_history_reads_the_conversation_oldest_first_without_events(tmp_path):
    from silentdesk.apps.slack.domain.slack import HistoryEntry

    keyring = FileKeyring(tmp_path / "keyring.json")
    api = FakeApi({})
    api.entries = [
        HistoryEntry("U0", None, "On it <@U2>", "20.0", None),
        HistoryEntry("U2", None, "joined", "15.0", "channel_join"),
        HistoryEntry("U2", None, "Can you check &lt;prod&gt;?", "10.0", None),
    ]
    app = Slack(
        api,
        FakeAuthorization(),
        KeyringCredentials(keyring),
        SqlcipherStateStore(SqlcipherDatabase(tmp_path / "db", keyring)),
    )
    asyncio.run(app.connect({}))

    messages = asyncio.run(app.history("D1"))

    assert [(m.key, m.direction, m.author, m.text) for m in messages] == [
        ("10.0", Direction.INBOUND, "Bo", "Can you check <prod>?"),
        ("20.0", Direction.OUTBOUND, "someone", "On it @Bo"),
    ]
