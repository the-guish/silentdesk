"""HTTPS for every app: the system certificate store and proxy settings, so
corporate TLS inspection keeps working (core principle 2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes = field(repr=False)

    def json(self) -> Any:
        raise NotImplementedError


class Http:
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json: Any = None,
    ) -> Response:
        """Sends one request. Only https URLs, except loopback addresses for tests."""
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError
