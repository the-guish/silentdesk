# SilentDesk core for Apple platforms

SilentDesk's core logic, in Swift, with the `silentdesk` command line from [spec/cli.md](../../spec/cli.md). The SwiftUI app in [`../app`](../app) will use it through the `SilentDeskCore` library only.

It needs Swift 6: Xcode 16 or newer on macOS, or the toolchain from [swift.org/install](https://www.swift.org/install/) on Linux. SQLCipher comes from [Zetetic's Swift package](https://github.com/sqlcipher/SQLCipher.swift) on Apple platforms, and from the distribution on Linux, with OpenSSL for hashing (`apt install libsqlcipher-dev libssl-dev` on Ubuntu), so the core builds and runs there too and can be developed without a Mac; CI builds it on both.

```sh
swift build                           # from this folder
.build/debug/silentdesk version       # {"contract":1,"implementation":"swift","version":"0.1.0"}
swift test                            # unit tests
```

| Path | What it is |
|------|------------|
| `Sources/CSQLCipher/`, `Sources/COpenSSL/` | The distribution's SQLCipher and OpenSSL, as system libraries, for the Linux build ([spec/storage.md](../../spec/storage.md)) |
| `Sources/SilentDeskCore/API.swift` | The public API: one function per command, and the wiring of every app |
| `Sources/SilentDeskCore/Contract/` | Protocols and data the apps expose to each other and to `API` |
| `Sources/SilentDeskCore/Support/` | JSON, RFC 3339 dates and encodings on Foundation, SHA-256 on CryptoKit or OpenSSL, and two async primitives |
| `Sources/SilentDeskCore/Adapters/` | Adapters every app can be given: settings, the SQLCipher database, the keyring, HTTPS, OAuth sign-in, the browser |
| `Sources/SilentDeskCore/Apps/Desk/` | The orchestration app: one queue of topics, and sync rounds over every connector |
| `Sources/SilentDeskCLI/` | The command line: parses arguments and prints JSON |
| `Sources/silentdesk/` | The program's entry point |
| `Tests/` | Unit tests for what the conformance suite cannot see |
| `Scripts/` | `sync-migrations.sh` embeds `spec/sql` into the core |
| `conformance-pending.txt` | Conformance cases this core does not pass yet |

## Layout

Everything lives in one module, laid out as the Python core is ([linux/core/README.md](../../linux/core/README.md)). Every app has the same six folders, and every folder may also use `Contract`:

| Folder | Holds | May use |
|--------|-------|---------|
| `Domain` | The app's data types, such as `GmailMessage` | nothing else |
| `Core` | Pure logic on that data, no I/O | `Domain` |
| `Ports` | Protocols for what the app needs from outside, used only inside the app | `Domain` |
| `Application` | The use cases, implementing the app's protocols in `Contract` | `Core`, `Ports`, `Domain` |
| `Adapters` | The ports' implementations | `Ports`, `Domain` |
| `Wiring` | `create()`, which builds the application with its adapters; `API.swift` calls it | everything in the app |

Apps never use each other, nor anything else in the core but `Contract` and `Support`: the shared services they need (settings, the database, the keyring, HTTPS, the browser) are protocols in `Contract`, which `Adapters/` implements and `API.swift` passes in. Only `API`, `Desk`, `LocalSettings`, the data types and the errors are public.

## Platform services

- **Secrets** live in the Keychain on Apple platforms, under the service `com.silentdesk.app`. On Linux the Python core, with Secret Service, is the one that ships; this core runs there with the test keyring only (`SILENTDESK_TEST_KEYRING`).
- **The database** is `silentdesk.db` in `~/Library/Application Support/SilentDesk/` on macOS, or `$XDG_DATA_HOME/silentdesk/` where that is set, as on Linux.
- **SQLCipher** is Zetetic's binary on Apple platforms, through the `SQLCipher` module, and the distribution's library on Linux, through `CSQLCipher`. The database is keyed with `PRAGMA key`, so the core needs only the standard SQLite API, which both expose, and one `#if canImport` picks the module.
- **Hashing** for PKCE is CryptoKit's SHA-256 on Apple platforms and OpenSSL's on Linux.
- **Sign-in** opens the default browser with `open` on macOS and `xdg-open` on Linux, and listens on the loopback interface for the redirect. The app will bring its own browser session.

The conformance suite is in [`spec/`](../../spec).
