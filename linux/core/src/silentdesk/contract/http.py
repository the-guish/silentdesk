"""HTTPS requests to the services the apps connect."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes = field(repr=False)


class Http(ABC):
    @abstractmethod
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

    @abstractmethod
    async def close(self) -> None: ...
