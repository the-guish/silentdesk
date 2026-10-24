# SilentDesk — CLI contract

Status: v1 scaffold · Last updated: 2026-10-24

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

## Planned

Not part of the contract yet:

- **Options for repeatable runs**, arriving with storage and the first source: a data directory, a fixed clock, and a base URL per service so the suite can point the cores at a fake server.
- **The legacy backend's methods** (`topics.list`, `<source>.sync`, `gmail.reply` and the rest, see [legacy/docs/specs/backend.md](../legacy/docs/specs/backend.md)), ported one by one as commands.
