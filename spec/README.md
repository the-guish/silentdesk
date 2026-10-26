# SilentDesk — Core contract

SilentDesk has two cores that must behave the same:

| Core | Language | Used by |
|------|----------|---------|
| [`linux/core`](../linux/core) | Python | the GTK app in [`linux/gtk`](../linux/gtk) |
| [`apple/core`](../apple/core) | Swift | the SwiftUI app in [`apple/app`](../apple/app) (deferred) |

This folder and [`docs/specs`](../docs/specs) define that behaviour without depending on either language. Each core ships a `silentdesk` command line that prints JSON, and the conformance suite runs the same cases against both.

| Path | What it is |
|------|------------|
| [`docs/specs/core.md`](../docs/specs/core.md) | The core principles. Every change follows them |
| [`docs/specs/sync.md`](../docs/specs/sync.md) | When the cores sync, and in what order |
| [`docs/specs/integrations/`](../docs/specs/integrations) | What each connector shows and does |
| [`docs/specs/cli.md`](../docs/specs/cli.md) | Commands, output, errors and exit codes |
| [`schema/`](schema) | JSON Schema for every command's output |
| [`docs/specs/filters.md`](../docs/specs/filters.md) | The filter bar both apps show over the topics |
| [`docs/specs/storage.md`](../docs/specs/storage.md) | The shared SQLite database (not decided yet) |
| [`conformance/`](conformance) | The test cases, as data |
| [`runner/`](runner) | Runs the cases against any core's `silentdesk` |

## Changing behaviour

1. Change the contract first: [`docs/specs/cli.md`](../docs/specs/cli.md), a schema, and a new or changed case.
2. Implement it in the Python core.
3. Implement it in the Swift core, or list the case in [`apple/core/conformance-pending.txt`](../apple/core/conformance-pending.txt) until it does.

The Python core is the reference until the Swift core passes every case.

## Running the suite

```sh
uv run spec/runner/conformance.py -- linux/core/.venv/bin/silentdesk
uv run spec/runner/conformance.py --pending apple/core/conformance-pending.txt -- apple/core/.build/debug/silentdesk
```

See [`conformance/README.md`](conformance/README.md) for the case format.
