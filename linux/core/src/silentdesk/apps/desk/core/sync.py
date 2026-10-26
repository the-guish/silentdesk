"""Sync rounds. See spec/sync.md."""

from __future__ import annotations

from collections.abc import Iterable

# Gmail goes last, because its first sync can take minutes.
ORDER = ("tasks", "github", "jira", "slack", "gmail")


def round_order(services: Iterable[str]) -> list[str]:
    """The connected services in the order one round syncs them: the ones in
    ORDER first, in that order, then any others by name."""
    services = set(services)
    return [service for service in ORDER if service in services] + sorted(services - set(ORDER))
