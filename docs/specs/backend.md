# SilentDesk — Backend

Status: v1 implemented · Last updated: 2026-10-24

SilentDesk runs as three parts:

| Part | Language | Does |
|------|----------|------|
| UI | TypeScript (React) | Shows topics and settings. Calls one Tauri command, `call`. |
| Host | Rust (Tauri) | Keeps all data and secrets, starts and supervises the backend, relays calls and events. |
| Backend | Python | Every source (Gmail, Google Tasks, Slack, Jira, GitHub), sync rounds, sign-in flows. |

```
UI ──invoke("call")──▶ Rust ──stdin/stdout, JSON lines──▶ Python
   ◀──── events ─────       ◀── store / secrets / browser / emit ──
```

## Rules

- **Rust owns all persistence.** The encrypted vault (`vault.bin`) and the OS credential store are only touched by Rust. Python has no files, caches or databases of its own.
- **Python writes through Rust's schemas.** Rust defines the data model (`src-tauri/src/model.rs`); Python mirrors it (`backend/silentdesk/core/model.py`). Rust rejects any write that does not match it exactly: an unknown field, a missing field or a wrong type. Change both files together.
- **Secrets live in Python's memory only.** Rust reads the source tokens from the credential store at startup and sends them in `init`. When Python gets a new token (sign-in, refresh) or drops one (disconnect, revoked grant), it asks Rust to save or delete it. The vault key never leaves Rust.
- **The webview never sees tokens.** It only gets account status and topic data, as before.

## Python layout (ports and adapters)

```
backend/silentdesk/
  core/        domain: model, errors, topic logic, ports (Store, Secrets, Browser, Events, Config)
  sources/     one package per source: domain.py (pure logic on VaultData), api.py (HTTP),
               service.py (the source's use cases), oauth.py where it signs in
  adapters/    rust.py (IPC and the port implementations), http.py, oauth.py (PKCE, loopback)
  app.py       method table and automatic sync rounds
  __main__.py  composition root
```

Sources depend on ports, never on the IPC. Tests (`backend/tests`) use in-memory fakes and mocked HTTP.

## Protocol

One JSON object per line, UTF-8, over the backend's stdin (Rust → Python) and stdout (Python → Rust). Anything else the backend prints goes to stderr, which the app logs.

| Message | Shape |
|---------|-------|
| Request | `{"id": 7, "method": "jira.sync", "params": {...}}` |
| Response | `{"id": 7, "result": ...}` or `{"id": 7, "error": {"kind": "...", "message": "..."}}` |
| Notification | `{"method": "emit", "params": {...}}`, no reply |

Ids are per sender. A message without `method` is a response.

### Rust → Python

| Method | Params | Result |
|--------|--------|--------|
| `init` | `secrets: {name: value}`, `config: {googleClientId, googleClientSecret, slackClientId, slackRedirectPort}` | `null`. Always the first request. Starts automatic syncing. |
| `<source>.status` / `.connect` / `.sync` / `.disconnect` | Connect takes the form's fields (`site`, `email`, `token`, …) | `ServiceStatus`, or topics for `sync` |
| `gmail.trash` / `gmail.reply` | `messageId`, `body` | topics / `null` |
| `slack.history` / `gmail.thread` | `topicId` | the conversation's or thread's messages, oldest first, read live and never stored |
| `topics.list` | | topics |
| `sync.soon` / `sync.refresh` / `sync.running` / `sync.lastSynced` | | see docs/specs/sync.md |

The UI reaches these through `invoke("call", {method, params})`. Rust refuses `init` from the UI.

### Python → Rust

| Method | Params | Result |
|--------|--------|--------|
| `store.read` | | `{revision, data}`: the whole `VaultData` |
| `store.write` | `{revision, data}` | `{revision}`. Fails with kind `conflict` if anything was written since `revision`; the writer reads again and retries. |
| `secrets.set` | `{name, value}` | `null`. Only the five source token names are accepted. |
| `secrets.delete` | `{name}` | `null` |
| `browser.open` | `{url}` | `null`. `https` only, for sign-in pages. |
| `emit` (notification) | `{event, payload}` | Sent to the UI. Only `gmail-sync-progress`, `sync-finished`, `sync-round` and `topics-updated`. |

## Lifecycle

- Rust starts the backend when the app starts. UI calls wait (up to 20 s) until `init` is answered.
- If the backend exits, calls in flight fail with "The SilentDesk backend is not running", and Rust starts it again. Restarts back off from 1 s to 60 s. They return to 1 s once a run has lasted a minute.
- Closing the app closes the backend's stdin, and the backend exits.

## Running Python

| Build | Code | Interpreter |
|-------|------|-------------|
| Development | `backend/` in the source tree | `backend/.venv` (`uv sync --directory backend`; `./dev.sh` does it) |
| Release | the app's `backend` resource | a standalone Python bundled next to it (`scripts/bundle-backend.sh`, run by `pnpm release`) |

`SILENTDESK_BACKEND_DIR` and `SILENTDESK_PYTHON` override both. The interpreter runs with `-E -s`, so `PYTHON*` variables and the user's own packages are ignored.

The backend uses the system certificate store (`truststore`) and the system proxy settings, so corporate TLS inspection and proxies keep working (core principle 2).

## Open questions

- **macOS signing:** the bundled Python and its `.so` files must be signed with the app and notarized. Whether Tauri's signing step covers resources, or a separate `codesign` pass is needed, is not settled yet.
- **Windows:** `bundle-backend.sh` covers macOS and Linux only.
- **Plugins:** not needed in the short term. If they come, they would run in a second backend process with only their own secrets.
