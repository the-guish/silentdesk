"""HTTPS with the system certificate store and proxy settings, so corporate
TLS inspection keeps working (core principle 2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contract import Http, Response


class HttpsClient(Http):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json: Any = None,
    ) -> Response:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError
