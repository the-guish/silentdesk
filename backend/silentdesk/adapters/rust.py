"""The connection to the Rust side: JSON messages, one per line, over stdin
and stdout. See docs/specs/backend.md for the protocol.

Both sides send requests, and either side may have several in flight:

- request:      {"id": 7, "method": "jira.sync", "params": {...}}
- response:     {"id": 7, "result": ...}
                {"id": 7, "error": {"kind": "notConnected", "message": "..."}}
- notification: {"method": "emit", "params": {...}}  (no reply)

Ids are per sender, so a message is a response exactly when it has no
`method`.

This module also holds the adapters for the ports Rust implements: storage,
secrets, the browser and UI events.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import sys
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ..core import errors
from ..core.model import VaultData, from_json, to_json

T = TypeVar("T")

# `store.read` carries the whole local data; keep well above its size.
MAX_MESSAGE_BYTES = 256 * 1024 * 1024
# A store write retries this often when another writer got in first.
WRITE_ATTEMPTS = 5
# Set SILENTDESK_DEBUG=1 to log each call's method and outcome to stderr.
# Params and results are never logged: they can hold tokens or messages.
DEBUG = os.environ.get("SILENTDESK_DEBUG") == "1"

Handler = Callable[[str, dict[str, Any]], Awaitable[Any]]


class Peer:
    """One end of the connection: sends requests and notifications, matches
    responses, and hands incoming requests to `handler`."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._tasks: set[asyncio.Task] = set()

    def _send(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        self._writer.write(line.encode() + b"\n")

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[id] = future
        self._send({"id": id, "method": method, "params": params})
        try:
            return await future
        finally:
            self._pending.pop(id, None)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"method": method, "params": params})

    async def serve(self, handler: Handler) -> None:
        """Reads messages until the other side closes the connection."""
        while line := await self._reader.readline():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print("silentdesk: ignoring a malformed message", file=sys.stderr)
                continue
            if "method" not in message:
                self._resolve(message)
            elif "id" in message:
                task = asyncio.create_task(self._answer(handler, message))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        for future in self._pending.values():
            if not future.done():
                future.set_exception(errors.Host("the app closed the connection."))

    def _resolve(self, message: dict[str, Any]) -> None:
        future = self._pending.get(message.get("id"))
        if future is None or future.done():
            return
        if "error" in message:
            error = message["error"] or {}
            exc_type = StoreConflict if error.get("kind") == "conflict" else errors.Host
            future.set_exception(exc_type(error.get("message", "the app refused the request.")))
        else:
            future.set_result(message.get("result"))

    async def _answer(self, handler: Handler, message: dict[str, Any]) -> None:
        id, method = message["id"], message["method"]
        try:
            result = await handler(method, message.get("params") or {})
            self._send({"id": id, "result": result})
            if DEBUG:
                print(f"silentdesk: {method}: ok", file=sys.stderr)
        except errors.AppError as e:
            self._send({"id": id, "error": {"kind": e.kind, "message": e.message}})
            if DEBUG:
                print(f"silentdesk: {method}: {e.kind}", file=sys.stderr)
        except Exception:  # noqa: BLE001 - reported to the caller, logged
            # Details go to the log, which never receives tokens; the UI gets
            # a generic message.
            traceback.print_exc(file=sys.stderr)
            self._send(
                {"id": id, "error": {"kind": "internal", "message": "Something went wrong. See the log for details."}}
            )


async def connect_stdio() -> Peer:
    """Wires a `Peer` to this process's stdin and stdout. Anything else
    printed to stdout would corrupt the protocol, so fd 1 is pointed at
    stderr and the protocol keeps a private copy of the original."""
    loop = asyncio.get_running_loop()
    protocol_out = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

    reader = asyncio.StreamReader(limit=MAX_MESSAGE_BYTES)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, protocol_out)
    writer = asyncio.StreamWriter(transport, protocol, None, loop)
    return Peer(reader, writer)


# --- Port adapters ----------------------------------------------------------


class StoreConflict(errors.Host):
    """Another writer saved since this one read."""


class RustStore:
    """`Store` over IPC. Rust checks each write against its schema and
    against the revision the data was read at."""

    def __init__(self, peer: Peer):
        self._peer = peer
        # Writers in this process take turns, so conflicts only come from
        # elsewhere.
        self._lock = asyncio.Lock()

    async def _read(self) -> tuple[int, VaultData]:
        reply = await self._peer.request("store.read", {})
        return reply["revision"], from_json(VaultData, reply["data"])

    async def read(self) -> VaultData:
        return (await self._read())[1]

    async def update(self, change: Callable[[VaultData], T]) -> T:
        async with self._lock:
            for _ in range(WRITE_ATTEMPTS):
                revision, data = await self._read()
                out = change(data)
                try:
                    await self._peer.request("store.write", {"revision": revision, "data": to_json(data)})
                    return out
                except StoreConflict:
                    continue
            raise errors.Host("Local data kept changing while saving. Try again.")


class RustSecrets:
    """`Secrets` over IPC. Rust sends every stored secret at startup; this
    keeps them in memory and asks Rust to save each change."""

    def __init__(self, peer: Peer, initial: dict[str, str]):
        self._peer = peer
        self._values = dict(initial)

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    async def set(self, name: str, value: str) -> None:
        await self._peer.request("secrets.set", {"name": name, "value": value})
        self._values[name] = value

    async def delete(self, name: str) -> None:
        await self._peer.request("secrets.delete", {"name": name})
        self._values.pop(name, None)


class RustBrowser:
    def __init__(self, peer: Peer):
        self._peer = peer

    async def open(self, url: str) -> None:
        try:
            await self._peer.request("browser.open", {"url": url})
        except errors.Host:
            raise errors.Auth("could not open your web browser.") from None


class RustEvents:
    def __init__(self, peer: Peer):
        self._peer = peer

    def emit(self, event: str, payload: Any) -> None:
        self._peer.notify("emit", {"event": event, "payload": to_json(payload)})
