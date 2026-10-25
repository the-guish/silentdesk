# SilentDesk core for Apple platforms

SilentDesk's core logic, in Swift, with the `silentdesk` command line from [spec/cli.md](../../spec/cli.md). The SwiftUI app in [`../app`](../app) will use it through the `SilentDeskCore` library only.

It needs Swift 6 and nothing else: Xcode 16 or newer on macOS, or the toolchain from [swift.org/install](https://www.swift.org/install/) on Linux. It builds and runs on Linux too, so it can be developed without a Mac; CI builds it on both.

```sh
swift build                           # from this folder
.build/debug/silentdesk version       # {"contract":1,"implementation":"swift","version":"0.1.0"}
swift test                            # unit tests
```

| Path | What it is |
|------|------------|
| `Sources/SilentDeskCore/API.swift` | The public API: one function per command |
| `Sources/SilentDeskCore/Contract/` | Protocols and data the apps expose to each other and to `API` |
| `Sources/SilentDeskCore/Support/` | JSON, RFC 3339 dates and encodings on Foundation, and two async primitives |
| `Sources/SilentDeskCore/Adapters/` | Adapters every app can be given; so far, settings from the environment |
| `Sources/SilentDeskCLI/` | The command line: parses arguments and prints JSON |
| `Sources/silentdesk/` | The program's entry point |
| `Tests/` | Unit tests for what the conformance suite cannot see |
| `conformance-pending.txt` | Conformance cases this core does not pass yet |

## Layout

Everything lives in one module, laid out as the Python core is ([linux/core/README.md](../../linux/core/README.md)). Every app, under `Sources/SilentDeskCore/Apps/`, has the same six folders, and every folder may also use `Contract`:

| Folder | Holds | May use |
|--------|-------|---------|
| `Domain` | The app's data types, such as `GmailMessage` | nothing else |
| `Core` | Pure logic on that data, no I/O | `Domain` |
| `Ports` | Protocols for what the app needs from outside, used only inside the app | `Domain` |
| `Application` | The use cases, implementing the app's protocols in `Contract` | `Core`, `Ports`, `Domain` |
| `Adapters` | The ports' implementations | `Ports`, `Domain` |
| `Wiring` | `create()`, which builds the application with its adapters; `API.swift` calls it | everything in the app |

Apps never use each other, nor anything else in the core but `Contract` and `Support`: the shared services they need (settings, the database, the keyring, HTTPS, the browser) are protocols in `Contract`, which `Adapters/` implements and `API.swift` passes in. Only `API`, `Desk`, `LocalSettings`, the data types and the errors are public.

The conformance suite is in [`spec/`](../../spec).
