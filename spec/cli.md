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
| `usage` | 2 | The command line is wrong. |
| `internal` | 1 | Anything unexpected. |

`message` is for people. Tests check that it is there, not what it says.

## Environment

| Variable | Meaning |
|----------|---------|
| `SILENTDESK_GOOGLE_CLIENT_ID` | The Google OAuth client that Gmail and Google Tasks sign in with. Unset or empty: those services are not configured. |
| `SILENTDESK_GOOGLE_CLIENT_SECRET` | That client's secret, if it has one. |
| `SILENTDESK_TEST_KEYRING` | **Tests only.** A JSON file used instead of the OS credential store; see below. |

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
  {"service": "gmail", "configured": true, "connected": false, "account": null},
  {"service": "tasks", "configured": true, "connected": false, "account": null}
]
```

| Field | Type | Notes |
|-------|------|-------|
| `service` | string | The service's name: `gmail` or `tasks` so far. |
| `configured` | boolean | The core has what it needs to sign in: for Google services, a client ID. |
| `connected` | boolean | A sign-in is stored: for Google services, a refresh token in the keyring. |
| `account` | string \| null | The connected account, such as an email address. `null` when not connected. |

## Planned

Not part of the contract yet:

- **Options for repeatable runs**, arriving with storage and the first sync: a fixed clock, and a base URL per service so the suite can point the cores at a fake server.
- **The legacy backend's methods** (`topics.list`, `<source>.sync`, `gmail.reply` and the rest, see [legacy/docs/specs/backend.md](../legacy/docs/specs/backend.md)), ported one by one as commands.
