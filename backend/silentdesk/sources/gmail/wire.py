"""Reading Google's JSON replies the way the Rust side's serde types did: a
missing field takes its default, but a reply that lacks a required field,
or has one of the wrong type, fails as a whole, as a network error. Shared
by Gmail, Google sign-in and Google Tasks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from ...core import errors

_MISSING = object()


class Malformed(Exception):
    """The reply does not have the expected shape."""


def read_json[T](response: httpx.Response, parse: Callable[[Any], T]) -> T:
    """The body of `response`, decoded by `parse`. Like reqwest's `json()`,
    a body that does not decode is a network error."""
    try:
        return parse(response.json())
    except (ValueError, Malformed):
        raise errors.Network("error decoding response body") from None


def obj(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Malformed
    return value


def _typed(value: Any, kind: type) -> Any:
    # `bool` is an `int` in Python; serde keeps them apart.
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        raise Malformed
    return value


def string(o: dict[str, Any], key: str, default: Any = _MISSING) -> str:
    """A string field. Required unless `default` is given."""
    value = o.get(key, _MISSING)
    if value is _MISSING:
        if default is _MISSING:
            raise Malformed
        return default
    return _typed(value, str)


def opt_string(o: dict[str, Any], key: str) -> str | None:
    """An optional string field: missing or `null` is `None`."""
    value = o.get(key)
    return None if value is None else _typed(value, str)


def boolean(o: dict[str, Any], key: str) -> bool:
    """A boolean field, `false` when missing."""
    value = o.get(key, _MISSING)
    return False if value is _MISSING else _typed(value, bool)


def items[T](o: dict[str, Any], key: str, parse: Callable[[Any], T]) -> list[T]:
    """A list field, empty when missing."""
    value = o.get(key, _MISSING)
    if value is _MISSING:
        return []
    return [parse(v) for v in _typed(value, list)]


def strings(o: dict[str, Any], key: str) -> list[str]:
    return items(o, key, lambda v: _typed(v, str))
