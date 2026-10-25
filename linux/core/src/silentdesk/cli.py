"""`silentdesk`: the JSON command line specified in spec/cli.md. Each
command is a thin wrapper around the matching function in `api`."""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import json
import sys
import traceback
from collections.abc import Callable, Sequence
from typing import Any

from . import api
from .contract import StorageError

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


class UsageError(Exception):
    pass


def _no_arguments(command: str, args: list[str]) -> None:
    if args:
        raise UsageError(f"{command} takes no arguments.")


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


def plain(value: Any) -> Any:
    """`value` as JSON-ready data: dataclasses become objects with camelCase
    keys, as spec/cli.md requires, and enums their values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {_camel(field.name): plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def _version(args: list[str]) -> Any:
    _no_arguments("version", args)
    return api.version()


def _services(args: list[str]) -> Any:
    _no_arguments("services", args)
    return plain(asyncio.run(api.desk().services()))


def _topics(args: list[str]) -> Any:
    _no_arguments("topics", args)
    return plain(asyncio.run(api.desk().topics()))


COMMANDS: dict[str, Callable[[list[str]], Any]] = {
    "services": _services,
    "topics": _topics,
    "version": _version,
}


def _error(kind: str, message: str) -> dict[str, Any]:
    return {"error": {"kind": kind, "message": message}}


def run(argv: Sequence[str]) -> tuple[int, Any]:
    """Runs one command line; returns the exit code and the document to print."""
    names = ", ".join(COMMANDS)
    try:
        if not argv:
            raise UsageError(f"Missing command. Commands: {names}.")
        command, *args = argv
        handler = COMMANDS.get(command)
        if handler is None:
            raise UsageError(f"Unknown command {command!r}. Commands: {names}.")
        return EXIT_OK, handler(args)
    except UsageError as error:
        return EXIT_USAGE, _error("usage", str(error))
    except StorageError as error:
        return EXIT_FAILED, _error("storage", str(error))
    except Exception as error:  # noqa: BLE001 - every failure must still print a JSON document
        traceback.print_exc()
        return EXIT_FAILED, _error("internal", str(error) or type(error).__name__)


def main() -> None:
    code, document = run(sys.argv[1:])
    json.dump(document, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)
