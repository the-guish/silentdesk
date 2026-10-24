"""Runs `python -m silentdesk` as the app does and plays the Rust side of
the protocol: init, storage with revisions, secrets and events."""

import asyncio
import json
import os
import sys
from pathlib import Path

from silentdesk.core.model import VaultData, to_json

BACKEND_DIR = Path(__file__).resolve().parent.parent


class FakeRust:
    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.next_id = 1
        self.pending: dict[int, asyncio.Future] = {}
        self.data = to_json(VaultData())
        self.revision = 0
        self.secrets: dict[str, str] = {}
        self.events: list[tuple[str, object]] = []
        self.requests: list[str] = []

    def send(self, message: dict) -> None:
        self.process.stdin.write(json.dumps(message).encode() + b"\n")

    async def call(self, method: str, params: dict | None = None):
        id = self.next_id
        self.next_id += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[id] = future
        self.send({"id": id, "method": method, "params": params or {}})
        return await asyncio.wait_for(future, 10)

    def answer(self, method: str, params: dict):
        self.requests.append(method)
        if method == "store.read":
            return {"revision": self.revision, "data": self.data}, None
        if method == "store.write":
            if params["revision"] != self.revision:
                return None, {"kind": "conflict", "message": "changed"}
            self.data = params["data"]
            self.revision += 1
            return {"revision": self.revision}, None
        if method == "secrets.set":
            self.secrets[params["name"]] = params["value"]
            return None, None
        if method == "secrets.delete":
            self.secrets.pop(params["name"], None)
            return None, None
        return None, {"kind": "host", "message": f"unknown method {method}"}

    async def serve(self) -> None:
        while line := await self.process.stdout.readline():
            message = json.loads(line)
            if "method" not in message:
                future = self.pending.pop(message["id"])
                if "error" in message:
                    future.set_exception(RuntimeError(message["error"]["message"]))
                else:
                    future.set_result(message["result"])
            elif "id" in message:
                result, error = self.answer(message["method"], message["params"])
                reply = {"id": message["id"], "error": error} if error else {"id": message["id"], "result": result}
                self.send(reply)
            else:
                self.events.append((message["params"]["event"], message["params"]["payload"]))


async def scenario():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-E",
        "-s",
        "-u",
        "-m",
        "silentdesk",
        cwd=BACKEND_DIR,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    rust = FakeRust(process)
    serving = asyncio.create_task(rust.serve())
    try:
        try:
            await rust.call("topics.list")
            raise AssertionError("calls before init must fail")
        except RuntimeError as e:
            assert "still starting" in str(e)

        await rust.call("init", {"secrets": {"github-token": "ghp_x"}, "config": {}})
        assert await rust.call("topics.list") == []

        status = await rust.call("jira.status")
        assert status == {"configured": True, "connected": False, "account": None}
        status = await rust.call("gmail.status")
        assert status["configured"] is False

        try:
            await rust.call("jira.sync")
            raise AssertionError("jira is not connected")
        except RuntimeError as e:
            assert str(e) == "Jira is not connected."

        try:
            await rust.call("nope.nothing")
            raise AssertionError("unknown methods must fail")
        except RuntimeError as e:
            assert "Unknown method" in str(e)

        # The automatic round started at init and announced itself.
        for _ in range(100):
            if ("sync-round", {"running": False}) in rust.events:
                break
            await asyncio.sleep(0.05)
        assert ("sync-round", {"running": True}) in rust.events
        assert await rust.call("sync.running") is False
        assert await rust.call("sync.lastSynced") is not None
    finally:
        process.stdin.close()
        assert await asyncio.wait_for(process.wait(), 10) == 0
        serving.cancel()
    return rust


def test_backend_speaks_the_protocol():
    rust = asyncio.run(scenario())
    # Nothing but protocol messages reached stdout (json.loads would fail).
    assert "store.read" in rust.requests


def test_store_retries_after_a_conflict():
    from silentdesk.adapters.rust import Peer, RustStore

    class Pipe:
        """Feeds a Peer's writes to a FakeRust-like handler in memory."""

        def __init__(self):
            self.reader = asyncio.StreamReader()
            self.revision = 0
            self.data = to_json(VaultData())
            self.conflicts_left = 1

        def write(self, raw: bytes) -> None:
            message = json.loads(raw)
            method, params = message["method"], message["params"]
            if method == "store.read":
                reply = {"result": {"revision": self.revision, "data": self.data}}
            elif self.conflicts_left:
                # Someone else writes first.
                self.conflicts_left -= 1
                self.revision += 1
                reply = {"error": {"kind": "conflict", "message": "changed"}}
            else:
                assert params["revision"] == self.revision
                self.data = params["data"]
                self.revision += 1
                reply = {"result": {"revision": self.revision}}
            self.reader.feed_data(json.dumps({"id": message["id"], **reply}).encode() + b"\n")

    async def run():
        pipe = Pipe()
        peer = Peer(pipe.reader, pipe)
        serving = asyncio.create_task(peer.serve(lambda m, p: None))
        store = RustStore(peer)
        calls = []

        def change(data):
            calls.append(1)
            data.gmail_history_id = "42"
            return "done"

        assert await store.update(change) == "done"
        serving.cancel()
        return pipe, calls

    pipe, calls = asyncio.run(run())
    assert len(calls) == 2
    assert pipe.data["gmailHistoryId"] == "42"
