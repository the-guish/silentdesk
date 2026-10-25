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
from .contract import ConnectorError, StorageError, SyncFailed, UnknownItem, UnknownService, UnknownTopic

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


# Every command takes its arguments and a function that reads stdin.
Command = Callable[[list[str], Callable[[], str]], Any]


def _version(args: list[str], stdin: Callable[[], str]) -> Any:
    _no_arguments("version", args)
    return api.version()


def _services(args: list[str], stdin: Callable[[], str]) -> Any:
    _no_arguments("services", args)
    return plain(asyncio.run(api.desk().services()))


def _topics(args: list[str], stdin: Callable[[], str]) -> Any:
    _no_arguments("topics", args)
    return plain(asyncio.run(api.desk().topics()))


def _one_service(command: str, args: list[str]) -> str:
    if len(args) != 1:
        raise UsageError(f"{command} takes one service name.")
    return args[0]


def _fields(text: str) -> dict[str, str]:
    """The connect fields: one JSON object of strings, or nothing."""
    if not text.strip():
        return {}
    try:
        fields = json.loads(text)
    except json.JSONDecodeError as error:
        raise UsageError(f"The connect fields on stdin are not JSON: {error}.") from error
    if not isinstance(fields, dict) or not all(isinstance(value, str) for value in fields.values()):
        raise UsageError("The connect fields on stdin must be one JSON object of strings.")
    return fields


def _connect(args: list[str], stdin: Callable[[], str]) -> Any:
    service = _one_service("connect", args)
    return plain(asyncio.run(api.desk().connect(service, _fields(stdin()))))


def _disconnect(args: list[str], stdin: Callable[[], str]) -> Any:
    return plain(asyncio.run(api.desk().disconnect(_one_service("disconnect", args))))


def _sync(args: list[str], stdin: Callable[[], str]) -> Any:
    if len(args) > 1:
        raise UsageError("sync takes at most one service name.")
    desk = api.desk()

    async def sync() -> str | None:
        await desk.sync(args[0] if args else None)
        return await desk.last_synced()

    return {"lastSynced": asyncio.run(sync())}


def _reply(args: list[str], stdin: Callable[[], str]) -> Any:
    if len(args) != 1:
        raise UsageError("reply takes one topic ID; the reply comes on stdin.")
    body = stdin()
    if not body.strip():
        raise UsageError("The reply is empty: write it on stdin.")
    asyncio.run(api.desk().reply(args[0], body))
    return {}


def _history(args: list[str], stdin: Callable[[], str]) -> Any:
    if len(args) != 1:
        raise UsageError("history takes one topic ID.")
    return plain(asyncio.run(api.desk().history(args[0])))


def _delete(args: list[str], stdin: Callable[[], str]) -> Any:
    if len(args) not in (1, 2):
        raise UsageError("delete takes one topic ID, and optionally one of its item keys.")
    if len(args) == 2:
        asyncio.run(api.desk().delete_item(args[0], args[1]))
    else:
        asyncio.run(api.desk().delete(args[0]))
    return {}


COMMANDS: dict[str, Command] = {
    "connect": _connect,
    "delete": _delete,
    "disconnect": _disconnect,
    "history": _history,
    "reply": _reply,
    "services": _services,
    "sync": _sync,
    "topics": _topics,
    "version": _version,
}


def _error(kind: str, message: str) -> dict[str, Any]:
    return {"error": {"kind": kind, "message": message}}


def _failure(service: str, error: Exception) -> dict[str, str]:
    kind = error.kind if isinstance(error, ConnectorError) else "internal"
    return {"service": service, "kind": kind, "message": str(error) or type(error).__name__}


def run(argv: Sequence[str], stdin: Callable[[], str] = lambda: sys.stdin.read()) -> tuple[int, Any]:
    """Runs one command line; returns the exit code and the document to print."""
    names = ", ".join(COMMANDS)
    try:
        if not argv:
            raise UsageError(f"Missing command. Commands: {names}.")
        command, *args = argv
        handler = COMMANDS.get(command)
        if handler is None:
            raise UsageError(f"Unknown command {command!r}. Commands: {names}.")
        return EXIT_OK, handler(args, stdin)
    except (UsageError, UnknownService, UnknownTopic, UnknownItem) as error:
        return EXIT_USAGE, _error("usage", str(error))
    except ConnectorError as error:
        return EXIT_FAILED, _error(error.kind, str(error))
    except SyncFailed as error:
        document = _error("sync", str(error))
        document["error"]["failures"] = [_failure(service, failure) for service, failure in error.failures]
        return EXIT_FAILED, document
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
