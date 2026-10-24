"""Errors returned to the UI. Messages must never contain secrets (tokens,
keys) or message contents.

Each error has a `kind`, sent to Rust next to the message, so callers can
tell them apart without parsing text.
"""


class AppError(Exception):
    kind = "error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotConfigured(AppError):
    kind = "notConfigured"

    def __init__(self, service: str, var: str, doc: str):
        super().__init__(f"{service} is not set up. Set {var} in .env (see docs/setup/{doc}.md).")


class NotConnected(AppError):
    kind = "notConnected"

    def __init__(self, service: str):
        super().__init__(f"{service} is not connected.")
        self.service = service


class Reauthorize(AppError):
    """The grant is dead: revoked, expired, or the token was deleted."""

    kind = "reauthorize"

    def __init__(self, service: str):
        super().__init__(f"{service} access was revoked or has expired. Connect again.")
        self.service = service


class MissingPermission(AppError):
    kind = "missingPermission"

    def __init__(self, service: str):
        super().__init__(f"{service} needs new permissions. Disconnect, then connect again.")


class UnknownMessage(AppError):
    kind = "unknownMessage"

    def __init__(self):
        super().__init__("That email is no longer in SilentDesk. Sync and try again.")


class EmptyReply(AppError):
    kind = "emptyReply"

    def __init__(self):
        super().__init__("Write a reply before sending.")


class AuthTimeout(AppError):
    kind = "authTimeout"

    def __init__(self):
        super().__init__("Sign-in timed out. Try again.")


class Auth(AppError):
    kind = "auth"

    def __init__(self, reason: str):
        super().__init__(f"Sign-in failed: {reason}")
        self.reason = reason


class Network(AppError):
    kind = "network"

    def __init__(self, detail: str):
        super().__init__(f"Network error: {detail}")


class Api(AppError):
    kind = "api"

    def __init__(self, service: str, status: int, message: str):
        super().__init__(f"{service} API error ({status}): {message}")
        self.service = service
        self.status = status


class Host(AppError):
    """The Rust side refused or failed a request: storage, keychain, browser."""

    kind = "host"
