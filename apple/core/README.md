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
| `Sources/SilentDeskCore/` | The public API: one function per command |
| `Sources/SilentDeskCLI/` | The command line: parses arguments and prints JSON |
| `Sources/silentdesk/` | The program's entry point |
| `Tests/` | Unit tests for what the conformance suite cannot see |
| `conformance-pending.txt` | Conformance cases this core does not pass yet |

The conformance suite is in [`spec/`](../../spec).
