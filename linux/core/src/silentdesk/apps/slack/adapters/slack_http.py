"""The few Slack Web API calls SilentDesk makes, all read-only."""

from __future__ import annotations

import json
from typing import Any

from ....contract import AuthError, Http, NetworkError, RemoteError
from ..domain.slack import HistoryEntry, Match, SlackAccount
from ..ports.slack_api import SlackApi

SERVICE = "slack"
TOKEN_ERRORS = ("invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive")


class SlackHttpApi(SlackApi):
    def __init__(self, http: Http, base_url: str) -> None:
        self.http = http
        # Such as https://slack.com/api.
        self.base = base_url

    async def _call(self, method: str, token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = await self.http.request(
            "GET", f"{self.base}/{method}", params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if response.status == 429:
            wait = response.headers.get("retry-after", "a few")
            raise RemoteError(SERVICE, f"Slack is rate limiting SilentDesk. Try again in {wait} seconds.", 429)
        try:
            body = json.loads(response.body)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise NetworkError(SERVICE, "Slack's answer could not be read.")
        if body.get("ok") is not True:
            error = body.get("error") or "unknown_error"
            if error in TOKEN_ERRORS:
                raise AuthError(SERVICE, "Slack rejected the token.")
            if error == "missing_scope":
                raise AuthError(SERVICE, "Slack did not grant this. Disconnect Slack and connect it again.")
            raise RemoteError(SERVICE, f"Slack answered {error}.", response.status)
        return body

    async def identity(self, token: str) -> SlackAccount:
        body = await self._call("auth.test", token)
        values = [body.get(key) for key in ("user_id", "user", "team_id", "team")]
        if not all(isinstance(value, str) for value in values):
            raise NetworkError(SERVICE, "Slack did not say who signed in.")
        return SlackAccount(*values)

    async def search(self, token: str, query: str, count: int) -> list[Match]:
        params = {"query": query, "sort": "timestamp", "sort_dir": "desc", "count": str(count)}
        found = (await self._call("search.messages", token, params)).get("messages", {})
        matches = found.get("matches", []) if isinstance(found, dict) else []
        return [_match(match) for match in matches if isinstance(match, dict) and isinstance(match.get("ts"), str)]

    async def history(self, token: str, channel_id: str, count: int) -> list[HistoryEntry]:
        found = (await self._call("conversations.history", token, {"channel": channel_id, "limit": str(count)})).get(
            "messages", []
        )
        return [
            HistoryEntry(
                user=m.get("user") if isinstance(m.get("user"), str) else None,
                username=m.get("username") if isinstance(m.get("username"), str) else None,
                text=str(m.get("text", "")),
                ts=m["ts"],
                subtype=m.get("subtype") if isinstance(m.get("subtype"), str) else None,
            )
            for m in found
            if isinstance(m, dict) and isinstance(m.get("ts"), str)
        ]

    async def user_name(self, token: str, user_id: str) -> str:
        try:
            user = (await self._call("users.info", token, {"user": user_id})).get("user", {})
        except (RemoteError, NetworkError):
            return ""
        profile = user.get("profile", {}) if isinstance(user, dict) else {}
        candidates = [profile.get("display_name"), profile.get("real_name"), user.get("real_name"), user.get("name")]
        return next((name for name in candidates if isinstance(name, str) and name.strip()), "")


def _match(value: dict[str, Any]) -> Match:
    channel = value.get("channel") if isinstance(value.get("channel"), dict) else {}
    return Match(
        channel_id=str(channel.get("id", "")),
        channel_name=str(channel.get("name", "")),
        is_im=value.get("type") == "im" or channel.get("is_im") is True,
        is_mpim=channel.get("is_mpim") is True,
        user=value.get("user") if isinstance(value.get("user"), str) else None,
        username=value.get("username") if isinstance(value.get("username"), str) else None,
        text=str(value.get("text", "")),
        ts=value["ts"],
        permalink=str(value.get("permalink", "")),
    )
