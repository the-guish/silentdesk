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
    assert problems == [
        "does not match error.json at $.error.kind: 'other' is not one of ['usage', 'auth', 'network', 'remote', 'unsupported', 'sync', 'storage', 'internal']"
    ]


def test_cases_run_in_a_throwaway_home():
    show_home = [sys.executable, "-c", "import json, os; print(json.dumps(os.environ['HOME']))"]
    problems = conformance.run_case({"args": [], "exit": 0, "schema": "error.json", "stdout": "x"}, show_home)
    assert any("silentdesk-conformance-" in problem for problem in problems)


def test_cases_set_their_own_environment(monkeypatch):
    monkeypatch.setenv("SILENTDESK_LEAK", "from the runner")
    show_env = [
        sys.executable,
        "-c",
        "import json, os; print(json.dumps([os.environ.get('SILENTDESK_LEAK'), os.environ['SILENTDESK_FILE']]))",
    ]
    problems = conformance.run_case(
        {
            "args": [],
            "exit": 0,
            "schema": "error.json",
            "env": {"SILENTDESK_FILE": "{home}/keyring.json"},
            "stdout": "x",
        },
        show_env,
    )
    assert any("[null, " in problem and "silentdesk-conformance-" in problem for problem in problems)


def test_cases_start_with_their_files(tmp_path):
    (tmp_path / "any.json").write_text("{}")
    show_files = [
        sys.executable,
        "-c",
        "import json; print(json.dumps([open('a/b.json').read(), open('c.txt').read()]))",
    ]
    case = {
        "args": [],
        "exit": 0,
        "schema": "any.json",
        "files": {"a/b.json": {"k": 1}, "c.txt": "text"},
        "stdout": ['{"k": 1}', "text"],
    }
    assert conformance.run_case(case, show_files, schemas=tmp_path) == []


# A stub core that echoes its stdin as JSON, after fetching $SILENTDESK_URL/<argv[1]> when given.
FETCHER = [
    sys.executable,
    "-c",
    """
import json, os, sys, urllib.request
reply = None
if len(sys.argv) > 1:
    request = urllib.request.Request(os.environ["SILENTDESK_URL"] + sys.argv[1], headers={"Authorization": "Bearer t"})
    try:
        reply = json.load(urllib.request.urlopen(request))
    except urllib.error.HTTPError as error:
        reply = error.code
print(json.dumps({"stdin": sys.stdin.read(), "reply": reply}))
""",
]


def fetch_case(steps: list[dict], **fields) -> dict:
    return {
        "env": {"SILENTDESK_URL": "{server}"},
        "steps": [{"schema": "any.json", **step} for step in steps],
        **fields,
    }


def test_steps_share_the_fake_server_and_get_their_stdin(tmp_path):
    (tmp_path / "any.json").write_text("{}")
    case = fetch_case(
        http=[
            {"path": "/github/user", "body": {"login": "ana"}},
            {"path": "/search", "query": {"q": "a"}, "body": [1]},
        ],
        steps=[
            {
                "args": ["/github/user"],
                "stdin": {"token": "t"},
                "exit": 0,
                "stdout": {"stdin": '{"token": "t"}', "reply": {"login": "ana"}},
            },
            {"args": ["/search?q=a&page=2"], "exit": 0, "stdout": {"stdin": "", "reply": [1]}},
            {"args": ["/search?q=b"], "exit": 0, "stdout": {"stdin": "", "reply": 404}},
        ],
        requests=[
            {"path": "/github/user", "headers": {"Authorization": "Bearer t"}},
            {"path": "/search", "query": {"q": "a", "page": "2"}},
            {"path": "/search"},
        ],
    )
    assert conformance.run_case(case, FETCHER, schemas=tmp_path) == []


def test_a_failing_step_is_named_and_unexpected_requests_are_reported(tmp_path):
    (tmp_path / "any.json").write_text("{}")
    case = fetch_case(
        steps=[{"args": ["/user"], "exit": 1, "stdout": {"stdin": "", "reply": 404}}],
        requests=[{"path": "/user", "headers": {"Authorization": "Bearer other"}}],
    )
    assert conformance.run_case(case, FETCHER, schemas=tmp_path) == [
        "step 1: exit code 0, expected 1",
        "request 1 (GET /user): header Authorization is 'Bearer t', expected 'Bearer other'",
    ]


def test_a_reply_can_redirect_with_values_from_the_request(tmp_path):
    (tmp_path / "any.json").write_text("{}")
    case = fetch_case(
        [
            {
                "args": ["/sign-in?redirect_uri=/done&state=s1"],
                "exit": 0,
                "stdout": {"stdin": "", "reply": {"code": "c"}},
            }
        ],
        http=[
            {"path": "/sign-in", "redirect": "{query.redirect_uri}?code=c&state={query.state}"},
            {"path": "/done", "query": {"state": "s1"}, "body": {"code": "c"}},
        ],
    )
    # urllib follows the redirect to {server}/done, relative to the server.
    assert conformance.run_case(case, FETCHER, schemas=tmp_path) == []


def test_steps_can_use_values_captured_from_earlier_output(tmp_path):
    (tmp_path / "any.json").write_text("{}")
    echo = [
        sys.executable,
        "-c",
        "import json, sys; print(json.dumps({'args': sys.argv[1:], 'stdin': sys.stdin.read()}))",
    ]
    case = {
        "steps": [
            {
                "args": ["first"],
                "schema": "any.json",
                "exit": 0,
                "stdout": {"args": ["first"], "stdin": ""},
                "capture": {"word": ["args", 0]},
            },
            {
                "args": ["again", "{capture.word}"],
                "stdin": "said {capture.word}",
                "schema": "any.json",
                "exit": 0,
                "stdout": {"args": ["again", "first"], "stdin": "said first"},
            },
        ]
    }
    assert conformance.run_case(case, echo, schemas=tmp_path) == []


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
