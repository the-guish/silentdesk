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
| `stdin` | Optional input: a string as is, anything else as JSON. |
| `env` | Optional environment variables for the run. In a value, `{home}` stands for the throwaway home folder and `{server}` for the fake server's address. |
| `files` | Optional files to create before the run, by path relative to the home folder: a string is written as text, anything else as JSON. |

### Several commands

A case with `steps` runs several commands in a row, in the same home folder and against the same fake server. Each step has its own `args`, `stdin`, `exit`, `schema` and `stdout`; `env`, `files`, `http` and `requests` belong to the case.

A step can keep values from its output for later steps: `"capture": {"topic": [0, "id"]}` keeps the first item's `id`, and `{capture.topic}` in a later step's `args` or `stdin` stands for it. Topic IDs are random, so this is how a case refers to one.

### The fake server

`http` lists the replies a fake server sends, which `{server}` in `env` points the core at:

```json
"http": [
  {"method": "GET", "path": "/github/user", "status": 200, "body": {"login": "ana"}},
  {"path": "/github/search/issues", "query": {"q": "is:pr is:open archived:false author:@me"}, "body": {"items": []}}
]
```

A reply answers every request with its `method` (default `GET`) and `path` whose query contains the reply's `query`; the first match wins. `status` defaults to 200, and a string `body` is sent as is. Any other request gets a 404.

A reply with `redirect` sends a 302 to that address instead, after replacing `{query.<name>}` with that query parameter of the request. A sign-in page can so send a test browser back to the core with the `state` it was given: `"redirect": "{query.redirect_uri}?code=c1&state={query.state}"`.

`requests`, if given, lists the requests the core must send, in order, and no others. Each names its `method` and `path`; its `query` and `headers` must be present in the request sent, and its `body`, if given, is compared as `stdout` is.

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

