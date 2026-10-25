"""OAuth sign-in through the browser, with PKCE and a one-shot listener on
the loopback interface for the redirect. Ported from the legacy backend."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import errno
import hashlib
import json
import secrets
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..contract import AuthError, Browser, Http, NetworkError, OAuth, OAuthClient, Tokens

SIGN_IN_TIMEOUT = 180.0
MAX_REQUEST_BYTES = 8 * 1024
READ_TIMEOUT = 5.0
NOT_FOUND = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Loopback:
    """Waits for the provider to redirect the browser back with a code."""

    def __init__(self, service: str, path: str, state: str) -> None:
        self.service, self.path, self.state = service, path, state
        self.redirect_uri = ""
        self._server: asyncio.Server | None = None
        self._outcome: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def start(self, port: int | None) -> None:
        try:
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", port or 0)
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise AuthError(self.service, f"Port {port} is already in use, so sign-in cannot start.") from error
            raise NetworkError(self.service, str(error)) from error
        actual = self._server.sockets[0].getsockname()[1]
        # Any-port providers (Google) take the address; fixed-port ones
        # (Slack) must match the registered URL, written with localhost.
        self.redirect_uri = f"http://localhost:{port}{self.path}" if port else f"http://127.0.0.1:{actual}"

    async def code(self, timeout: float) -> str:
        try:
            return await asyncio.wait_for(asyncio.shield(self._outcome), timeout)
        except TimeoutError:
            raise AuthError(self.service, "Sign-in did not finish in time. Try again.") from None

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None

    def _outcome_of(self, request_line: str) -> str | AuthError | None:
        """The code, the error to report, or None for anything that is not
        the redirect, such as the browser asking for a favicon."""
        parts = request_line.split()
        if len(parts) < 2 or parts[0] != "GET":
            return None
        url = urlsplit(parts[1])
        if url.path != self.path:
            return None
        params = dict(reversed(parse_qsl(url.query, keep_blank_values=True)))
        code, error = params.get("code"), params.get("error")
        if code is None and error is None:
            return None
        if params.get("state") != self.state:
            return AuthError(self.service, "The sign-in response did not match this request.")
        if error is not None:
            return AuthError(
                self.service, "Access was denied." if error == "access_denied" else f"Sign-in failed: {error}."
            )
        return code

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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
            lines = request.decode("utf-8", "replace").splitlines()
            outcome = self._outcome_of(lines[0] if lines else "")
            if outcome is None or self._outcome.done():
                writer.write(NOT_FOUND)
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
                + f"Content-Length: {len(body)}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n".encode()
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


class LoopbackOAuth(OAuth):
    def __init__(self, http: Http, browser: Browser, timeout: float = SIGN_IN_TIMEOUT) -> None:
        self.http = http
        self.browser = browser
        self.timeout = timeout

    async def sign_in(self, client: OAuthClient, scopes: Sequence[str]) -> Tokens:
        verifier = b64url(secrets.token_bytes(32))
        challenge = b64url(hashlib.sha256(verifier.encode()).digest())
        loopback = Loopback(client.service, client.path, b64url(secrets.token_bytes(16)))
        await loopback.start(client.port)
        try:
            query = {
                "client_id": client.client_id,
                "redirect_uri": loopback.redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": loopback.state,
                **client.extra,
            }
            try:
                await self.browser.open(f"{client.authorize_url}?{urlencode(query)}")
            except Exception as error:
                raise AuthError(client.service, "Your web browser could not be opened.") from error
            code = await loopback.code(self.timeout)
        finally:
            loopback.close()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": loopback.redirect_uri,
        }
        return await self._token(client, form)

    async def refresh(self, client: OAuthClient, refresh_token: str) -> Tokens:
        return await self._token(client, {"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def revoke(self, url: str, token: str) -> None:
        # Best effort: the local token goes either way.
        with contextlib.suppress(NetworkError):
            await self.http.request("POST", url, form={"token": token})

    async def _token(self, client: OAuthClient, form: dict[str, str]) -> Tokens:
        form["client_id"] = client.client_id
        if client.client_secret:
            form["client_secret"] = client.client_secret
        response = await self.http.request("POST", client.token_url, form=form, headers={"Accept": "application/json"})
        try:
            body: Any = json.loads(response.body)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise NetworkError(client.service, f"The sign-in server's answer could not be read ({response.status}).")
        if not 200 <= response.status < 300:
            error = body.get("error")
            if error == "invalid_grant":
                raise AuthError(client.service, "The sign-in has expired or was revoked. Connect again.")
            if error in ("invalid_client", "unauthorized_client"):
                raise AuthError(client.service, "The OAuth client was rejected. Check its client ID and secret.")
            raise AuthError(client.service, f"Sign-in failed: {error or response.status}.")
        access, refresh, scope = body.get("access_token"), body.get("refresh_token"), body.get("scope")
        return Tokens(
            access_token=access if isinstance(access, str) else None,
            refresh_token=refresh if isinstance(refresh, str) else None,
            scopes=tuple(scope.split()) if isinstance(scope, str) else (),
            raw=body,
        )
