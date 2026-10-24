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
from pathlib import Path
from typing import Any

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


def run_case(case: dict[str, Any], command: list[str], schemas: Path = SCHEMAS) -> list[str]:
    """Runs one case; returns what was wrong, or nothing if it passed."""
    with tempfile.TemporaryDirectory(prefix="silentdesk-conformance-") as home:
        write_files(Path(home), case.get("files", {}))
        try:
            process = subprocess.run(
                [*command, *case["args"]],
                check=False,
                cwd=home,
                env=isolated_env(home, case.get("env")),
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return [f"did not finish within {TIMEOUT_SECONDS} s"]

    problems = []
    if process.returncode != case["exit"]:
        problems.append(f"exit code {process.returncode}, expected {case['exit']}")
    try:
        stdout = process.stdout.decode("utf-8")
        document = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        problems.append(f"stdout is not one UTF-8 JSON document: {error}")
    else:
        if not stdout.endswith("\n"):
            problems.append("stdout does not end with a newline")
        schema = json.loads((schemas / case["schema"]).read_text())
        for error in jsonschema.Draft202012Validator(schema).iter_errors(document):
            problems.append(f"does not match {case['schema']} at {error.json_path}: {error.message}")
        problems += mismatches(case["stdout"], document)
    if problems and process.stderr:
        problems.append("stderr: " + process.stderr.decode("utf-8", "replace").strip()[-2000:])
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
