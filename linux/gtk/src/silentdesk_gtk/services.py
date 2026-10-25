"""What each service asks for to connect, and what can be done with its
topics. Pure, so it is tested without a display. The fields are those of
`silentdesk connect` in spec/cli.md."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from silentdesk.contract import ServiceStatus

from .format import service_name


@dataclass(frozen=True)
class Field:
    name: str
    title: str
    secret: bool = False
    required: bool = True


FIELDS: dict[str, list[Field]] = {
    "github": [
        Field("token", "Personal access token", secret=True),
        Field("server", "Enterprise Server host, empty for github.com", required=False),
    ],
    "jira": [
        Field("site", "Site, such as acme.atlassian.net"),
        Field("email", "Email, for Jira Cloud only", required=False),
        Field("token", "API token", secret=True),
    ],
}

# Services that sign in through the browser, and the variable naming the
# app they sign in with.
BROWSER_SIGN_IN = {
    "gmail": "SILENTDESK_GOOGLE_CLIENT_ID",
    "tasks": "SILENTDESK_GOOGLE_CLIENT_ID",
    "slack": "SILENTDESK_SLACK_CLIENT_ID",
}

# The services whose connectors can reply in a topic. Every other connector
# raises `Unsupported`, so the topic screen offers no reply box.
CAN_REPLY = frozenset({"gmail"})


@dataclass(frozen=True)
class Deletion:
    """How deleting a topic reads: the question that confirms it, and the
    toast once done."""

    heading: str
    body: str
    done: str


# The services whose connectors can delete a topic.
DELETIONS = {
    "gmail": Deletion(
        "Move this thread to the trash?",
        "Gmail keeps it in the trash for 30 days, then deletes it.",
        "Moved to the trash",
    ),
}


def fields(service: str) -> list[Field]:
    return FIELDS.get(service, [])


def missing(service: str, values: Mapping[str, str]) -> list[str]:
    """The titles of the required fields left empty."""
    return [field.title for field in fields(service) if field.required and not values.get(field.name, "").strip()]


def connect_params(service: str, values: Mapping[str, str]) -> dict[str, str]:
    """The fields to send, trimmed, without the empty optional ones."""
    trimmed = {field.name: values.get(field.name, "").strip() for field in fields(service)}
    return {name: value for name, value in trimmed.items() if value}


def describe(status: ServiceStatus) -> str:
    """One line under the service's name."""
    if status.connected:
        return status.account or "Connected"
    if not status.configured:
        variable = BROWSER_SIGN_IN.get(status.service)
        return f"Set {variable} to connect" if variable else "Not set up"
    if status.service in BROWSER_SIGN_IN:
        return "Not connected · signs in through your browser"
    return "Not connected"


def disconnect_warning(service: str) -> str:
    return f"SilentDesk forgets your {service_name(service)} sign-in and drops its topics."
