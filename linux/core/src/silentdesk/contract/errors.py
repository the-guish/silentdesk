"""Errors apps raise to each other and to the interfaces. Each connector
error has a `kind`, which the CLI reports as the error kind in spec/cli.md."""

from __future__ import annotations


class ConnectorError(Exception):
    kind = "internal"

    def __init__(self, service: str | None, message: str) -> None:
        super().__init__(message)
        # None when raised below any one app, as by the HTTPS client.
        self.service = service


class AuthError(ConnectorError):
    """The service is not connected, or it rejected the credentials."""

    kind = "auth"


class NetworkError(ConnectorError):
    """The service could not be reached, or its answer could not be read."""

    kind = "network"


class RemoteError(ConnectorError):
    """The service answered with an error."""

    kind = "remote"

    def __init__(self, service: str | None, message: str, status: int | None = None) -> None:
        super().__init__(service, message)
        self.status = status


class Unsupported(ConnectorError):
    """The service cannot do this, such as replying to a task."""

    kind = "unsupported"


class UnknownService(Exception):
    """No connector has this service name."""


class UnknownTopic(Exception):
    """No topic has this ID, or its service no longer knows it."""


class UnknownItem(Exception):
    """The topic has no item with this key."""


class UnknownProject(Exception):
    """No project has this ID."""


class InvalidProjectName(Exception):
    """A project name that is empty, taken, All or Default."""


class InvalidQuery(Exception):
    """A topics query with a value the core cannot read, such as a time
    that is not RFC 3339."""


class SyncFailed(Exception):
    """A sync round in which one or more services failed. The others synced."""

    def __init__(self, failures: list[tuple[str, Exception]]) -> None:
        count = len(failures)
        super().__init__(f"{count} service{'' if count == 1 else 's'} failed to sync.")
        self.failures = failures
