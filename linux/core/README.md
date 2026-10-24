# SilentDesk core for Linux

SilentDesk's core logic, in Python, with the `silentdesk` command line from [spec/cli.md](../../spec/cli.md). The GTK app in [`../gtk`](../gtk) uses it through `silentdesk.api` only.

It has no dependencies beyond the Python standard library yet. It needs Python 3.12 or newer, which is Ubuntu 24.04's.

```sh
uv sync                         # from this folder
.venv/bin/silentdesk version    # {"contract": 1, "implementation": "python", "version": "0.1.0"}
uv run pytest -q                # unit tests
```

| Path | What it is |
|------|------------|
| `src/silentdesk/api.py` | The public API: one function per command |
| `src/silentdesk/cli.py` | The command line: parses arguments and prints JSON |
| `tests/` | Unit tests for what the conformance suite cannot see |
| `conformance-pending.txt` | Conformance cases this core does not pass yet |

The conformance suite is in [`spec/`](../../spec).
