"""Unit tests for the CLI. Behaviour shared with the Swift core is tested by
the conformance suite in spec/; these cover what it cannot see."""

from silentdesk import api, cli


def test_version_reports_the_installed_package():
    from importlib.metadata import version

    assert api.version() == {"contract": api.CONTRACT, "implementation": "python", "version": version("silentdesk")}


def test_usage_errors_list_the_commands():
    code, document = cli.run(["no-such-command"])
    assert code == cli.EXIT_USAGE
    assert document["error"]["message"] == "Unknown command 'no-such-command'. Commands: services, version."


def test_unexpected_failures_are_internal_errors(monkeypatch):
    def broken(args):
        raise RuntimeError("Disk on fire.")

    monkeypatch.setitem(cli.COMMANDS, "version", broken)
    assert cli.run(["version"]) == (cli.EXIT_FAILED, {"error": {"kind": "internal", "message": "Disk on fire."}})
