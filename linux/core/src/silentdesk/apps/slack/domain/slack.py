"""Slack messages, as far as SilentDesk needs them. Message text is never
stored: only a preview of a conversation's newest message, as its title."""

from __future__ import annotations

from dataclasses import dataclass, field

from ....contract import Direction


@dataclass(frozen=True)
class Credential:
    """Without token rotation, a long-lived user token; with it, a 12-hour
    access token and a refresh token."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    # Unix seconds, or None when the token does not expire.
    expires_at: int | None


@dataclass(frozen=True)
class SlackAccount:
    user_id: str
    user_name: str
    team_id: str
    team_name: str


@dataclass(frozen=True)
class Match:
    """One search result, as Slack returns it."""

    channel_id: str
    # For a 1:1 DM, the other user's ID.
    channel_name: str
    is_im: bool
    is_mpim: bool
    user: str | None
    username: str | None
    # Slack's markup, with <@U1> mentions and <url|label> links.
    text: str
    ts: str
    permalink: str


@dataclass(frozen=True)
class DirectMessage:
    channel_id: str
    ts: str
    direction: Direction
    author: str
    # The other person, or "Group DM".
    counterpart: str
    # The start of the message as plain text.
    preview: str
    permalink: str
    # RFC 3339.
    date: str
