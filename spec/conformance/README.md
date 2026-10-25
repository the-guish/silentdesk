# Conformance cases

Each file in [`cases/`](cases) is one test. The runner starts a core's `silentdesk` with the case's arguments and checks what it prints.

```json
{
  "description": "version reports the contract this core implements",
  "args": ["version"],
  "exit": 0,
  "schema": "version.json",
  "stdout": {
    "contract": 1,
    "implementation": { "$any": "string" },
    "version": { "$any": "string" }
  }
}
```

| Field | Meaning |
|-------|---------|
| `description` | What the case checks, in one sentence. |
| `args` | The arguments passed to `silentdesk`. |
| `exit` | The expected exit code. |
| `schema` | The file in [`../schema`](../schema) that stdout must match. |
| `stdout` | The expected JSON document. |
| `env` | Optional environment variables for the run. `{home}` in a value stands for the throwaway home folder. |

## How stdout is compared

- Objects must have exactly the expected keys; key order does not matter.
- Arrays must have the same items in the same order.
- Numbers compare by value, so `1` equals `1.0`. `true` never equals `1`.
- `{"$any": "<type>"}` matches any value of that JSON type: `string`, `number`, `integer`, `boolean`, `object`, `array` or `null`. Use it for values that differ between cores, such as `version`, or that tests do not pin down, such as error messages.

## How each case runs

- In a fresh temporary directory, which is also `HOME` and the base of the `XDG_*` directories, so a core can never touch the user's real data.
- Without any `SILENTDESK_*` variables from the runner's own environment: only the case's `env` sets them.
- With a 30-second time limit.
- Pass the core's built program, not `uv run` or `swift run`: with a throwaway `HOME`, those tools would start from an empty cache.

## Pending cases

A core that does not pass a case yet lists its name in a pending file (`--pending`), one per line; `#` starts a comment. A pending case that fails is reported but does not fail the run. A pending case that passes does fail it, so the list only ever shrinks.

## Planned

Cases for commands that call Gmail, Slack, Jira, GitHub or Google Tasks will add an `http` section: the replies a fake server sends, and the requests the core is expected to make. The runner will serve them, so the same recordings test both cores.
