# SilentDesk core for Linux

SilentDesk's core logic, in Python, with the `silentdesk` command line from [spec/cli.md](../../spec/cli.md). The GTK app in [`../gtk`](../gtk) uses it through `silentdesk.api` only.

It needs Python 3.12 or newer, which is Ubuntu 24.04's. It depends on `keyring`, for the OS credential store, `sqlcipher3-binary`, for the encrypted database ([spec/storage.md](../../spec/storage.md)), and `httpx` with `truststore`, for HTTPS with the system's certificates; `src/silentdesk/sql` links to the shared migrations in `spec/sql/`.

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
| `src/silentdesk/apps/desk/` | The orchestration app: one queue of topics, its search and projects, and sync rounds over every connector |
| `src/silentdesk/adapters/` | Adapters every app can be given: settings, the SQLCipher database, the keyring, HTTPS, the browser |
| `tests/` | Unit tests, including the layout rules in `test_architecture.py` |
| `conformance-pending.txt` | Conformance cases this core does not pass yet |

## Layout

Every app has the same six folders. Every folder may also import `contract`:

| Folder | Holds | May import |
|--------|-------|------------|
| `domain` | The app's data types, such as `GmailMessage` | nothing else |
| `core` | Pure logic on that data, no I/O | `domain` |
| `ports` | Abstract classes for what the app needs from outside, used only inside the app | `domain` |
| `application` | The use cases, implementing the app's classes in `contract` | `core`, `ports`, `domain` |
| `adapters` | The ports' implementations | `ports`, `domain`, third-party packages |
| `wiring` | `create()`, which builds the application with its adapters; `api.py` calls it | everything in the app |

Apps never import each other, nor anything else in `silentdesk` but `contract`: the shared services they need (settings, the database, the keyring, HTTPS, the browser) are classes in `contract`, which `src/silentdesk/adapters/` implements and `api.py` passes in. `domain`, `core`, `ports`, `application` and `contract` use only the standard library. `tests/test_architecture.py` enforces these rules and checks that every abstract class has a concrete implementation; `uv run lint-imports` checks the same import rules.

Most methods still raise `NotImplementedError`: this is the skeleton the legacy backend's code moves into.

The conformance suite is in [`spec/`](../../spec).
