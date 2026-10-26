#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema>=4.23"]
# ///
"""Runs the conformance cases in spec/conformance/cases against one core's
`silentdesk`, and reports which ones it passes.

    uv run spec/runner/conformance.py [--pending FILE] [--case NAME] -- COMMAND...

COMMAND starts the core's built program, for example
linux/core/.venv/bin/silentdesk or apple/core/.build/debug/silentdesk.
The case format is described in spec/conformance/README.md."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self
from urllib.parse import parse_qsl, urlsplit

import jsonschema

SPEC = Path(__file__).resolve().parent.parent
CASES = SPEC / "conformance" / "cases"
SCHEMAS = SPEC / "schema"
TIMEOUT_SECONDS = 30


def is_type(value: Any, kind: str) -> bool:
    """Whether `value` is of the JSON type named `kind`."""
    match kind:
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "null":
            return value is None
    raise ValueError(f"Unknown JSON type in $any: {kind!r}")


def mismatches(expected: Any, actual: Any, path: str = "$") -> list[str]:
    """Every difference between the expected and actual documents, one line each."""
    if isinstance(expected, dict) and expected.keys() == {"$any"}:
        kind = expected["$any"]
        return [] if is_type(actual, kind) else [f"{path}: expected any {kind}, got {json.dumps(actual)}"]
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected an object, got {json.dumps(actual)}"]
        problems = [f"{path}.{key}: missing" for key in sorted(expected.keys() - actual.keys())]
        problems += [f"{path}.{key}: unexpected" for key in sorted(actual.keys() - expected.keys())]
        for key in sorted(expected.keys() & actual.keys()):
            problems += mismatches(expected[key], actual[key], f"{path}.{key}")
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected an array, got {json.dumps(actual)}"]
        if len(expected) != len(actual):
            return [f"{path}: expected {len(expected)} items, got {len(actual)}"]
        problems = []
        for index, (want, got) in enumerate(zip(expected, actual)):
            problems += mismatches(want, got, f"{path}[{index}]")
        return problems
    # Scalars. Python counts True as 1, JSON does not.
    if isinstance(expected, bool) or isinstance(actual, bool):
        same = type(expected) is type(actual) and expected == actual
    else:
        same = expected == actual
    return [] if same else [f"{path}: expected {json.dumps(expected)}, got {json.dumps(actual)}"]


def isolated_env(home: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The runner's environment with a throwaway home, so a core never
    touches the user's real data, and without SILENTDESK_* variables, so
    only the case decides them. `extra` adds the case's own variables, where
    "{home}" stands for the throwaway home."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("SILENTDESK_")}
    env.update(
        HOME=home,
        XDG_DATA_HOME=f"{home}/.local/share",
        XDG_CONFIG_HOME=f"{home}/.config",
        XDG_CACHE_HOME=f"{home}/.cache",
        XDG_STATE_HOME=f"{home}/.local/state",
    )
    env.update({name: value.replace("{home}", home) for name, value in (extra or {}).items()})
    return env


def write_files(home: Path, files: dict[str, Any]) -> None:
    """Writes a case's starting files, by path relative to its home: a string
    as text, anything else as JSON."""
    for relative, content in files.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))


class FakeServer:
    """Serves a case's `http` replies on a loopback port, and records every
    request the core sends. A reply answers every request with its method
    and path whose query contains the reply's `query`; the first match wins.
    Anything else gets a 404."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = replies
        self.requests: list[dict[str, Any]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def handle_one(self) -> None:
                url = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
                try:
                    body: Any = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    body = raw
                request = {
                    "method": self.command,
                    "path": url.path,
                    "query": dict(parse_qsl(url.query, keep_blank_values=True)),
                    "headers": {name.lower(): value for name, value in self.headers.items()},
                    "body": body,
                }
                server.requests.append(request)
                reply = server.reply_for(request)
                status = reply.get("status", 200) if reply else 404
                content = reply.get("body") if reply else {"message": "No fake reply for this request."}
                data = (content if isinstance(content, str) else json.dumps(content or {})).encode()
                self.send_response(302 if reply and "redirect" in reply else status)
                if reply and "redirect" in reply:
                    location = reply["redirect"]
                    for name, value in request["query"].items():
                        location = location.replace(f"{{query.{name}}}", value)
                    self.send_header("Location", location)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_one

            def log_message(self, *args: Any) -> None:
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"

    def reply_for(self, request: dict[str, Any]) -> dict[str, Any] | None:
        for reply in self.replies:
            if (
                reply.get("method", "GET") == request["method"]
                and reply["path"] == request["path"]
                and reply.get("query", {}).items() <= request["query"].items()
            ):
                return reply
        return None

    def __enter__(self) -> Self:
        threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.http.shutdown()
        self.http.server_close()


def request_mismatches(expected: list[dict[str, Any]] | None, actual: list[dict[str, Any]]) -> list[str]:
    """Checks the requests the core sent, in order. Each expected request
    names its method and path; its query and headers must be present in the
    actual one, and its body, if given, must match. An `any_order` group
    stands for requests sent concurrently: they come next, in any order,
    each paired by method and path."""
    if expected is None:
        return []
    groups = [want.get("any_order", [want]) for want in expected]
    count = sum(len(group) for group in groups)
    sent = [f"{r['method']} {r['path']}" for r in actual]
    if count != len(actual):
        return [f"sent {len(actual)} requests, expected {count}: {sent}"]
    problems, remaining = [], iter(enumerate(actual, 1))
    for group in groups:
        unpaired = list(group)
        for number, got in [next(remaining) for _ in group]:
            where = f"request {number} ({got['method']} {got['path']})"
            want = next((w for w in unpaired if label(w) == f"{got['method']} {got['path']}"), None)
            if want is None:
                problems.append(f"{where}: expected {' or '.join(label(w) for w in unpaired)}")
                continue
            unpaired.remove(want)
            problems += request_problems(where, want, got)
    return problems


def label(want: dict[str, Any]) -> str:
    return f"{want.get('method', 'GET')} {want['path']}"


def request_problems(where: str, want: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """What differs between an expected request and the one sent, apart from
    its method and path."""
    problems = []
    for name, value in want.get("query", {}).items():
        if got["query"].get(name) != value:
            problems.append(f"{where}: query {name} is {got['query'].get(name)!r}, expected {value!r}")
    for name, value in want.get("headers", {}).items():
        if got["headers"].get(name.lower()) != value:
            problems.append(f"{where}: header {name} is {got['headers'].get(name.lower())!r}, expected {value!r}")
    if "body" in want:
        problems += [f"{where}: body {problem}" for problem in mismatches(want["body"], got["body"])]
    return problems


def substitute(text: str, captured: dict[str, str]) -> str:
    for name, value in captured.items():
        text = text.replace(f"{{capture.{name}}}", value)
    return text


def capture(step: dict[str, Any], document: Any, captured: dict[str, str]) -> list[str]:
    """Keeps values from a step's output for later steps, by path, such as
    {"topic": [0, "id"]} for the first topic's ID."""
    problems = []
    for name, path in step.get("capture", {}).items():
        value = document
        try:
            for key in path:
                value = value[key]
        except (KeyError, IndexError, TypeError):
            problems.append(f"cannot capture {name}: nothing at {path}")
            continue
        captured[name] = value if isinstance(value, str) else json.dumps(value)
    return problems


def run_step(
    step: dict[str, Any], command: list[str], home: str, env: dict[str, str], schemas: Path, captured: dict[str, str]
) -> list[str]:
    """Runs one command of a case; returns what was wrong."""
    stdin = step.get("stdin")
    if stdin is not None and not isinstance(stdin, str):
        stdin = json.dumps(stdin)
    try:
        process = subprocess.run(
            [*command, *(substitute(arg, captured) for arg in step["args"])],
            check=False,
            cwd=home,
            env=env,
            input=substitute(stdin or "", captured).encode(),
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return [f"did not finish within {TIMEOUT_SECONDS} s"]

    problems = []
    if process.returncode != step["exit"]:
        problems.append(f"exit code {process.returncode}, expected {step['exit']}")
    try:
        stdout = process.stdout.decode("utf-8")
        document = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        problems.append(f"stdout is not one UTF-8 JSON document: {error}")
    else:
        if not stdout.endswith("\n"):
            problems.append("stdout does not end with a newline")
        schema = json.loads((schemas / step["schema"]).read_text())
        for error in jsonschema.Draft202012Validator(schema).iter_errors(document):
            problems.append(f"does not match {step['schema']} at {error.json_path}: {error.message}")
        problems += mismatches(step["stdout"], document)
        problems += capture(step, document, captured)
    if problems and process.stderr:
        problems.append("stderr: " + process.stderr.decode("utf-8", "replace").strip()[-2000:])
    return problems


def run_case(case: dict[str, Any], command: list[str], schemas: Path = SCHEMAS) -> list[str]:
    """Runs one case, every step in the same home and against the same fake
    server; returns what was wrong, or nothing if it passed."""
    steps = case.get("steps", [case])
    with (
        tempfile.TemporaryDirectory(prefix="silentdesk-conformance-") as home,
        FakeServer(case.get("http", [])) as server,
    ):
        write_files(Path(home), case.get("files", {}))
        extra = {name: value.replace("{server}", server.url) for name, value in case.get("env", {}).items()}
        env = isolated_env(home, extra)
        problems: list[str] = []
        captured: dict[str, str] = {}
        for number, step in enumerate(steps, 1):
            label = f"step {number}: " if "steps" in case else ""
            problems += [label + problem for problem in run_step(step, command, home, env, schemas, captured)]
        problems += request_mismatches(case.get("requests"), server.requests)
    return problems


def read_pending(path: Path) -> set[str]:
    names = set()
    for line in path.read_text().splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            names.add(name)
    return names


def run(command: list[str], cases_dir: Path, pending: set[str], only: list[str] | None) -> int:
    """Runs the cases and prints a report; returns the exit code."""
    cases = {path.stem: path for path in sorted(cases_dir.glob("*.json"))}
    unknown = sorted((pending | set(only or [])) - cases.keys())
    if unknown:
        print(f"No such case: {', '.join(unknown)}", file=sys.stderr)
        return 2

    passed = failed = still_pending = 0
    for name, path in cases.items():
        if only and name not in only:
            continue
        problems = run_case(json.loads(path.read_text()), command)
        if name in pending:
            if problems:
                still_pending += 1
                print(f"PENDING  {name}")
                continue
            problems = ["passes now: remove it from the pending list"]
        if problems:
            failed += 1
            print(f"FAIL     {name}")
            for problem in problems:
                print(f"           {problem}")
        else:
            passed += 1
            print(f"PASS     {name}")

    print(f"\n{passed} passed, {failed} failed, {still_pending} pending")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SilentDesk conformance cases against one core.")
    parser.add_argument("--pending", type=Path, help="file listing the cases this core does not pass yet")
    parser.add_argument("--case", action="append", dest="only", metavar="NAME", help="run only this case")
    parser.add_argument("command", nargs="+", help="how to start the core's silentdesk; put it after --")
    args = parser.parse_args(argv)

    program = args.command[0]
    if shutil.which(program) is None:
        print(f"Cannot run {program}: build the core first.", file=sys.stderr)
        return 2
    # Each case runs in its own directory, so a relative program path must be made absolute.
    if os.sep in program:
        args.command[0] = str(Path(program).resolve())

    pending = read_pending(args.pending) if args.pending else set()
    return run(args.command, CASES, pending, args.only)


if __name__ == "__main__":
    sys.exit(main())
