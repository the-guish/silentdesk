# SilentDesk — CLI contract

Status: v1 · Last updated: 2026-10-25

Both cores ship a program named `silentdesk`. The conformance suite tests each core through it. The apps reach the same operations through the core's public API (`silentdesk.api` in Python, `SilentDeskCore` in Swift), one function per command, and use nothing else from the core.

```
silentdesk <command> [arguments]
```

## Output

- **stdout** carries exactly one JSON document, followed by a newline, whether the command succeeds or fails. It is UTF-8.
- **stderr** is for people: logs and warnings. It is not part of the contract, and tests ignore it.
- Field names are camelCase.
- Timestamps are RFC 3339 in UTC, ending in `Z`.
- A field with no value is `null`. Fields are not left out unless a command says so.
- Key order, whitespace and number formatting (`1` or `1.0`) are not part of the contract.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | The command succeeded. |
| 1 | The command ran and failed. |
| 2 | Usage error: missing or unknown command, or wrong arguments. |

## Errors

On failure, stdout holds an error document ([schema](schema/error.json)):

```json
{"error": {"kind": "usage", "message": "Unknown command 'foo'. Commands: version."}}
```

| Kind | Exit code | When |
|------|-----------|------|
| `usage` | 2 | The command line is wrong, including an unknown service name or connect fields that are not a JSON object of strings. |
| `auth` | 1 | The service is not connected, or it rejected the credentials. A sync that gets this deletes the stored credentials. |
| `network` | 1 | The service could not be reached, or its answer could not be read. |
| `remote` | 1 | The service answered with an error. |
| `unsupported` | 1 | The service cannot do this, such as replying to a task. |
| `sync` | 1 | A sync round where one or more services failed; see below. |
| `storage` | 1 | The database cannot be opened, such as when its key is missing from the keyring ([storage.md](storage.md)). |
| `internal` | 1 | Anything unexpected. |

When a sync round fails, the error also lists each failed service, with the kind and message it would have had alone. The other services were synced.

```json
{"error": {"kind": "sync", "message": "1 service failed to sync.", "failures": [
  {"service": "github", "kind": "auth", "message": "GitHub rejected the token. Connect again."}
]}}
```

`message` is for people. Tests check that it is there, not what it says.

## Environment

| Variable | Meaning |
|----------|---------|
| `SILENTDESK_GOOGLE_CLIENT_ID` | The Google OAuth client that Gmail and Google Tasks sign in with. Unset or empty: those services are not configured. |
| `SILENTDESK_GOOGLE_CLIENT_SECRET` | That client's secret, if it has one. |
| `SILENTDESK_TEST_KEYRING` | **Tests only.** A JSON file used instead of the OS credential store; see below. |
| `SILENTDESK_TEST_BASE_URL` | **Tests only.** Every service's API at `<url>/<service>`, such as `<url>/github`, instead of its real address. Plain `http` is then allowed, to loopback addresses only. |
| `SILENTDESK_TEST_NOW` | **Tests only.** A fixed time, in RFC 3339, used instead of the clock. |

### Test keyring

Tests and CI cannot reach GNOME Keyring or the macOS Keychain, so when `SILENTDESK_TEST_KEYRING` is set, a core keeps its secrets in that file instead. The file holds one JSON object mapping entry names ([storage.md](storage.md#secrets)) to values; a missing file is an empty keyring. It stores secrets in plain text, against core principle 1, so it exists only for tests: nothing else may set it.

## Commands

### `version`

Takes no arguments. Reports which contract the core implements ([schema](schema/version.json)).

```json
{"contract": 1, "implementation": "python", "version": "0.1.0"}
```

| Field | Type | Notes |
|-------|------|-------|
| `contract` | integer | The version of this contract the core implements. Raised on every incompatible change. |
| `implementation` | `python` \| `swift` | Which core answered. |
| `version` | string | The core's own version. |

### `services`

Takes no arguments. Lists every service SilentDesk can connect, sorted by `service` ([schema](schema/services.json)).

```json
[
  {"service": "github", "configured": true, "connected": false, "account": null},
  {"service": "gmail", "configured": true, "connected": false, "account": null},
  {"service": "tasks", "configured": true, "connected": false, "account": null}
]
```

| Field | Type | Notes |
|-------|------|-------|
| `service` | string | The service's name: `github`, `gmail` or `tasks` so far. |
| `configured` | boolean | The core has what it needs to sign in: for Google services, a client ID. GitHub needs nothing: the user brings a token. |
| `connected` | boolean | A sign-in is stored: for Google services, a refresh token in the keyring; for GitHub, a token and its account. |
| `account` | string \| null | The connected account, such as an email address, or `login · host` for GitHub. `null` when not connected. |

### `topics`

Takes no arguments. Lists every topic, newest first: by `updatedAt`, then by `id`, both descending ([schema](schema/topics.json)). Creates the database on first use.

```json
[
  {
    "id": "5f0c…",
    "service": "gmail",
    "title": "Invoice for October",
    "items": [
      {"key": "18c2…", "direction": "inbound", "author": "Ana Ruiz", "url": null, "date": "2026-10-24T09:12:00Z"}
    ],
    "updatedAt": "2026-10-24T09:12:00Z"
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | SilentDesk's own ID for the topic, a UUID. |
| `service` | string | The service every item of the topic comes from. |
| `title` | string | |
| `items` | array | One or more, oldest first. |
| `items[].key` | string | The item's ID in its service, such as a Gmail message ID. |
| `items[].direction` | `inbound` \| `outbound` \| null | |
| `items[].author` | string \| null | Who wrote it, as shown to the user. |
| `items[].url` | string \| null | Opens the item in its own system. |
| `items[].date` | string | RFC 3339. |
| `updatedAt` | string | The newest item's date. |

### `connect <service>`

Connects one service. Reads the service's fields as one JSON object of strings on stdin, such as `{"token": "…"}`; empty input means no fields. Each service lists its fields in its own section. Prints the service's status, as one item of `services` ([schema](schema/status.json)).

| Service | Fields |
|---------|--------|
| `github` | `token`: a personal access token, required. `server`: a GitHub Enterprise Server host, such as `github.acme.com`; empty or missing for github.com. |

### `disconnect <service>`

Disconnects one service: forgets its credentials, its stored state and its topics. Prints the service's status ([schema](schema/status.json)).

### `sync [service]`

Syncs one service, or, without an argument, every connected service in turn: Google Tasks, GitHub, Jira, Slack, then Gmail. Prints when topics last changed ([schema](schema/sync.json)).

```json
{"lastSynced": "2026-10-24T12:00:00Z"}
```

## Planned

Not part of the contract yet:

- **Options for repeatable runs**, arriving with storage and the first sync: a fixed clock, and a base URL per service so the suite can point the cores at a fake server.
- **The legacy backend's methods** (`topics.list`, `<source>.sync`, `gmail.reply` and the rest, see [legacy/docs/specs/backend.md](../legacy/docs/specs/backend.md)), ported one by one as commands.
