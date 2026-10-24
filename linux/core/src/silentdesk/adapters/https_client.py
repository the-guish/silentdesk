"""HTTPS with the system certificate store and proxy settings, so corporate
TLS inspection keeps working (core principle 2)."""

from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Mapping
from importlib.metadata import version
from typing import Any

import httpx
import truststore

from ..contract import Http, NetworkError, Response

TIMEOUT = httpx.Timeout(30.0)


def is_loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


class HttpsClient(Http):
    def __init__(self, allow_loopback_http: bool = False, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """`allow_loopback_http` lets tests reach a fake server over plain
        http on this machine. `transport` replaces the network in unit tests."""
        self.allow_loopback_http = allow_loopback_http
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        # Created on first use, inside the event loop that will use it.
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": f"SilentDesk/{version('silentdesk')}"},
                timeout=TIMEOUT,
                follow_redirects=True,
                verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                transport=self._transport,
                # Checks every request before it is sent, redirects included.
                event_hooks={"request": [self._check]},
            )
        return self._client

    async def _check(self, request: httpx.Request) -> None:
        url = request.url
        if url.scheme == "https" or (url.scheme == "http" and self.allow_loopback_http and is_loopback(url.host)):
            return
        raise httpx.UnsupportedProtocol(f"Only https addresses are allowed: {url}", request=request)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        form: Mapping[str, str] | None = None,
    ) -> Response:
        try:
            response = await self._http().request(method, url, headers=headers, params=params, json=json, data=form)
        except httpx.HTTPError as error:
            raise NetworkError(None, str(error) or type(error).__name__) from error
        return Response(response.status_code, dict(response.headers), response.content)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
