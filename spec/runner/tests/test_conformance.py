"""Tests for the conformance runner itself, against a stub program that
prints whatever JSON and exit code it is given."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conformance

STUB = [sys.executable, "-c", "import sys; print(sys.argv[1]); sys.exit(int(sys.argv[2]))"]


def case(stdout: str, exit: int = 0, expected: object = None, schema: str = "error.json") -> dict:
    """A case whose stub prints `stdout` and exits with `exit`."""
    if expected is None:
        expected = json.loads(stdout)
    return {"description": "test", "args": [stdout, str(exit)], "exit": 0, "schema": schema, "stdout": expected}


ERROR = '{"error": {"kind": "usage", "message": "Bad."}}'
ANY_ERROR = {"error": {"kind": "usage", "message": {"$any": "string"}}}


def test_any_matches_by_json_type():
    assert conformance.mismatches({"$any": "string"}, "x") == []
    assert conformance.mismatches({"$any": "integer"}, 3) == []
    assert conformance.mismatches({"$any": "integer"}, True) != []
    assert conformance.mismatches({"$any": "number"}, 1.5) == []
    assert conformance.mismatches({"$any": "null"}, None) == []


def test_reports_missing_and_unexpected_keys():
    assert conformance.mismatches({"a": 1, "b": 2}, {"a": 1, "c": 2}) == ["$.b: missing", "$.c: unexpected"]


def test_numbers_compare_by_value_but_booleans_are_not_numbers():
    assert conformance.mismatches({"n": 1}, {"n": 1.0}) == []
    assert conformance.mismatches({"n": 1}, {"n": True}) == ["$.n: expected 1, got true"]


def test_arrays_compare_in_order():
    assert conformance.mismatches([1, 2], [1, 2]) == []
    assert conformance.mismatches([1, 2], [2, 1]) == ["$[0]: expected 1, got 2", "$[1]: expected 2, got 1"]
    assert conformance.mismatches([1], [1, 2]) == ["$: expected 1 items, got 2"]


def test_case_passes():
    assert conformance.run_case(case(ERROR, expected=ANY_ERROR), STUB) == []


def test_case_fails_on_exit_code():
    assert conformance.run_case(case(ERROR, exit=1), STUB) == ["exit code 1, expected 0"]


def test_case_fails_when_stdout_is_not_json():
    [problem] = conformance.run_case(case("not json", expected={}), STUB)
    assert problem.startswith("stdout is not one UTF-8 JSON document")


def test_case_fails_when_stdout_breaks_the_schema():
    document = '{"error": {"kind": "other", "message": "Bad."}}'
    problems = conformance.run_case(case(document), STUB)
    assert problems == ["does not match error.json at $.error.kind: 'other' is not one of ['usage', 'internal']"]


def test_cases_run_in_a_throwaway_home():
    show_home = [sys.executable, "-c", "import json, os; print(json.dumps(os.environ['HOME']))"]
    problems = conformance.run_case({"args": [], "exit": 0, "schema": "error.json", "stdout": "x"}, show_home)
    assert any("silentdesk-conformance-" in problem for problem in problems)


@pytest.fixture
def cases_dir(tmp_path: Path) -> Path:
    (tmp_path / "passes.json").write_text(json.dumps(case(ERROR)))
    (tmp_path / "fails.json").write_text(json.dumps(case(ERROR, exit=1)))
    return tmp_path


def test_run_fails_when_a_case_fails(cases_dir, capsys):
    assert conformance.run(STUB, cases_dir, pending=set(), only=None) == 1
    assert "1 passed, 1 failed, 0 pending" in capsys.readouterr().out


def test_failing_pending_case_does_not_fail_the_run(cases_dir, capsys):
    assert conformance.run(STUB, cases_dir, pending={"fails"}, only=None) == 0
    assert "1 passed, 0 failed, 1 pending" in capsys.readouterr().out


def test_passing_pending_case_fails_the_run(cases_dir, capsys):
    assert conformance.run(STUB, cases_dir, pending={"passes"}, only=["passes"]) == 1
    assert "passes now: remove it from the pending list" in capsys.readouterr().out


def test_unknown_case_names_are_rejected(cases_dir):
    assert conformance.run(STUB, cases_dir, pending={"nope"}, only=None) == 2
