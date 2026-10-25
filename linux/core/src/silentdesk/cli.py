"""`silentdesk`: the JSON command line specified in spec/cli.md. Each
command is a thin wrapper around the matching function in `api`."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import traceback
from collections.abc import Callable, Sequence
from typing import Any

from . import api

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


class UsageError(Exception):
    pass


def _version(args: list[str]) -> Any:
    if args:
        raise UsageError("version takes no arguments.")
    return api.version()


def _services(args: list[str]) -> Any:
    if args:
        raise UsageError("services takes no arguments.")
    return [dataclasses.asdict(status) for status in asyncio.run(api.desk().services())]


COMMANDS: dict[str, Callable[[list[str]], Any]] = {
    "services": _services,
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
    except Exception as error:  # noqa: BLE001 - every failure must still print a JSON document
        traceback.print_exc()
        return EXIT_FAILED, _error("internal", str(error) or type(error).__name__)


def main() -> None:
    code, document = run(sys.argv[1:])
    json.dump(document, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)
