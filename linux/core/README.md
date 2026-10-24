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
| `src/silentdesk/api.py` | The public API: one function per command, and the wiring of every app |
| `src/silentdesk/cli.py` | The command line: parses arguments and prints JSON |
| `src/silentdesk/contract/` | Abstract classes and data the apps expose to each other and to `api` |
| `src/silentdesk/apps/gmail/` | The Gmail connector |
| `src/silentdesk/apps/google_tasks/` | The Google Tasks connector |
| `src/silentdesk/apps/desk/` | The orchestration app: one queue of topics, and sync rounds over every connector |
| `src/silentdesk/infra/` | Shared technical pieces for adapters: settings, the SQLCipher database, the keyring, HTTPS, the browser |
| `tests/` | Unit tests, including the layout rules in `test_architecture.py` |
| `conformance-pending.txt` | Conformance cases this core does not pass yet |

## Layout

Every app has the same four layers, and its package `__init__` wires them together:

| Layer | Holds | May import |
|-------|-------|------------|
| `core` | The domain: data and pure logic, no I/O | `contract` |
| `ports` | Abstract classes for what the app needs from outside, used only inside the app | `contract`, `core` |
| `adapters` | The ports' implementations | `contract`, `core`, `ports`, `infra`, third-party packages |
| `application` | The use cases, implementing the app's classes in `contract` | `contract`, `core`, `ports` |

Apps never import each other; they meet only through `contract`. `core`, `ports`, `application` and `contract` use only the standard library. `tests/test_architecture.py` enforces these rules, and checks that every abstract class has a concrete implementation.

Most methods still raise `NotImplementedError`: this is the skeleton the legacy backend's code moves into.

The conformance suite is in [`spec/`](../../spec).
