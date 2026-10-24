# SilentDesk

A quiet desktop task tracker for work. It pulls your email, chat messages, issues, pull requests and tasks into one queue of topics.

SilentDesk is moving from one Tauri app to two native apps: Python with GTK4 on Linux, and Swift on macOS. Both share one contract, tested by one suite.

## Layout

| Path | What it is | Status |
|------|------------|--------|
| [`spec/`](spec) | The contract both cores follow, and the conformance suite that tests them | Scaffold |
| [`linux/core/`](linux/core) | Core logic and JSON command line, in Python | Scaffold |
| [`linux/gtk/`](linux/gtk) | The Linux app: GTK4 and libadwaita, in Python, on `linux/core` | Scaffold |
| [`apple/core/`](apple/core) | Core logic and JSON command line, in Swift | Scaffold |
| [`apple/app/`](apple/app) | The macOS app, in SwiftUI, on `apple/core`; iOS may follow | Deferred |
| [`docs/`](docs) | Notes for the native apps, such as [open-source apps on the Mac App Store](docs/apple-store-reference-apps.md) | Reference |
| [`legacy/`](legacy) | The current Tauri app, unchanged. It works until the new apps replace it | Working |

The product specs and core principles are still in [`legacy/docs/`](legacy/docs).

## Quick start

You need [uv](https://docs.astral.sh/uv/). For the Swift core, you also need Swift 6 (Xcode 16 or newer on macOS; on Linux, see [swift.org/install](https://www.swift.org/install/)).

```sh
# Python core
uv sync --directory linux/core
linux/core/.venv/bin/silentdesk version

# Linux app: needs the system packages listed in linux/gtk/README.md
linux/gtk/run.sh

# Swift core
swift build --package-path apple/core
apple/core/.build/debug/silentdesk version

# Conformance suite, against either core
uv run spec/runner/conformance.py -- linux/core/.venv/bin/silentdesk
uv run spec/runner/conformance.py -- apple/core/.build/debug/silentdesk
```

To run the legacy app, see [`legacy/README.md`](legacy/README.md).

## License

Apache License 2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [AUTHORS](AUTHORS).
