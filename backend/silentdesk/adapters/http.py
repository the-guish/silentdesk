"""The HTTP client every source API adapter uses: HTTPS only, the system's
certificate store and proxy settings, a 30-second timeout."""

from __future__ import annotations

import ssl

import httpx
import truststore

from .. import __version__
from ..core import errors

USER_AGENT = f"SilentDesk/{__version__}"
TIMEOUT = httpx.Timeout(30.0)


async def _https_only(request: httpx.Request) -> None:
    if request.url.scheme != "https":
        raise httpx.UnsupportedProtocol("only https URLs are allowed", request=request)


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """`transport` replaces the network in tests (`httpx.MockTransport`)."""
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        event_hooks={"request": [_https_only]},
        transport=transport,
    )


async def send(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """Sends a request, turning connection failures into `errors.Network`.
    HTTP error statuses are returned, not raised: each API decides what they
    mean."""
    try:
        return await client.request(method, url, **kwargs)
    except httpx.HTTPError as e:
        raise errors.Network(str(e) or type(e).__name__) from None
