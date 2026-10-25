"""HTTPS requests to the services the apps connect."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
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
        # A list repeats the parameter, as in ?a=1&a=2.
        params: Mapping[str, str | Sequence[str]] | None = None,
        json: Any = None,
        form: Mapping[str, str] | None = None,
    ) -> Response:
        """Sends one request, with a `json` or `form` body if given. Only
        https URLs, except loopback addresses when tests allow it. Raises
        NetworkError when the service cannot be reached; error statuses are
        returned, for each app to interpret."""

    @abstractmethod
    async def close(self) -> None: ...
