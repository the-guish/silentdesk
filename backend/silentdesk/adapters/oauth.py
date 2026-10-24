"""OAuth 2.0 building blocks shared by every integration: PKCE (RFC 7636)
and the loopback redirect for native apps (RFC 8252). The browser does the
sign-in, so SilentDesk never sees the user's password, and SSO or MFA work
as usual."""

from __future__ import annotations

import asyncio
import base64
import errno
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from ..core import errors

SIGN_IN_TIMEOUT = 180.0
MAX_REQUEST_BYTES = 8 * 1024
READ_TIMEOUT = 5.0


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str


def pkce() -> Pkce:
    verifier = b64url(secrets.token_bytes(32))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    return Pkce(verifier, challenge)


def state() -> str:
    """An unguessable value tying the redirect to the request that started
    it."""
    return b64url(secrets.token_bytes(16))


def parse_callback(request_line: str, path: str, expected_state: str) -> str | errors.AppError | None:
    """Parses `GET <path>?code=...&state=... HTTP/1.1`. Returns the code, the
    error to report, or `None` when the request is not an OAuth redirect at
    all."""
    parts = request_line.split()
    if len(parts) < 2 or parts[0] != "GET":
        return None
    url = urlsplit(parts[1])
    if url.path != path:
        return None
    params: dict[str, str] = {}
    for k, v in parse_qsl(url.query, keep_blank_values=True):
        params.setdefault(k, v)
    code, error, got_state = params.get("code"), params.get("error"), params.get("state")
    if code is None and error is None:
        return None
    if got_state != expected_state:
        return errors.Auth("the sign-in response did not match this request.")
    if error is not None:
        return errors.Auth("access was denied." if error == "access_denied" else error)
    return code


_NOT_FOUND = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


class Loopback:
    """A one-shot HTTP listener on the loopback interface that waits for the
    provider to redirect the browser back with an authorization code."""

    def __init__(self, path: str):
        self.path = path
        self.redirect_uri = ""
        self._server: asyncio.Server | None = None
        self._state = ""
        self._outcome: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    @classmethod
    async def any_port(cls) -> Loopback:
        """Random free port, root path: `http://127.0.0.1:<port>`. For
        providers that accept any loopback port (Google)."""
        self = cls("/")
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.redirect_uri = f"http://127.0.0.1:{port}"
        return self

    @classmethod
    async def fixed(cls, port: int, path: str, port_var: str) -> Loopback:
        """Fixed port and path: `http://localhost:<port><path>`. For
        providers that match the registered redirect URL exactly (Slack)."""
        self = cls(path)
        try:
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                raise errors.Auth(
                    f"port {port} is already in use. Set {port_var} to a free port and update "
                    "the app's redirect URL to match."
                ) from None
            raise errors.Network(str(e)) from None
        self.redirect_uri = f"http://localhost:{port}{path}"
        return self

    async def wait_for_code(self, expected_state: str) -> str:
        """Waits for the redirect carrying `expected_state`, up to the
        sign-in timeout."""
        self._state = expected_state
        try:
            return await asyncio.wait_for(asyncio.shield(self._outcome), SIGN_IN_TIMEOUT)
        except TimeoutError:
            raise errors.AuthTimeout() from None
        finally:
            self.close()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Answers one connection. Requests that are not the OAuth redirect
        (a browser's favicon fetch, for example) get 404."""
        try:
            request = b""
            while len(request) < MAX_REQUEST_BYTES and b"\r\n\r\n" not in request:
                try:
                    chunk = await asyncio.wait_for(reader.read(MAX_REQUEST_BYTES - len(request)), READ_TIMEOUT)
                except TimeoutError:
                    break
                if not chunk:
                    break
                request += chunk
            if not self._state:
                writer.write(_NOT_FOUND)
                return
            lines = request.decode("utf-8", "replace").splitlines()
            outcome = parse_callback(lines[0] if lines else "", self.path, self._state)
            if outcome is None or self._outcome.done():
                writer.write(_NOT_FOUND)
                return
            message = (
                "Sign-in received. You can close this tab and return to SilentDesk."
                if isinstance(outcome, str)
                else "Sign-in did not complete. Return to SilentDesk for details."
            )
            body = (
                "<!doctype html><meta charset=utf-8><title>SilentDesk</title>"
                f'<body style="font-family:system-ui;margin:3rem"><p>{message}</p>'
            ).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Connection: close\r\nCache-Control: no-store\r\n\r\n"
                + body
            )
            if isinstance(outcome, str):
                self._outcome.set_result(outcome)
            else:
                self._outcome.set_exception(outcome)
        finally:
            try:
                await writer.drain()
            except ConnectionError:
                pass
            writer.close()
