# SilentDesk for macOS

The macOS app, in SwiftUI. It reaches the core in [`../core`](../core) through `SilentDeskCore` only, and behaves as the GTK app in [linux/gtk](../../linux/gtk/README.md) does.

It needs macOS 14 or newer. It is a Swift package, not an Xcode project, so it builds with `swift build` and CI can make the app without a Mac.

This folder holds the app's model for now: what the windows show and do, without SwiftUI. The windows come next.

| Path | What it is |
|------|------------|
| `Sources/SilentDeskAppModel/` | What the windows show and do, without SwiftUI, so it builds and is tested on Linux too |
| `Sources/SilentDeskAppModel/QueueModel.swift` | The queue, search, Refresh and automatic syncing |
| `Sources/SilentDeskAppModel/TopicModel.swift` | The topic screen: items or conversation, reply and delete |
| `Sources/SilentDeskAppModel/ServicesModel.swift` | The Services settings: connect forms and Disconnect |
| `Sources/SilentDeskAppModel/Format.swift`, `Services.swift` | How topics read, and what each service asks for and offers |
| `Sources/SilentDeskAppModel/AppSettings.swift` | The core's settings: the environment, then the app's defaults |
| `Sources/SilentDeskAppModel/DemoDesk.swift` | Made-up topics, for `--demo` and the screenshots |

## Build

```sh
swift test                      # from this folder
```

It runs on a Mac with Xcode 16 or newer. On Linux, it builds and tests `SilentDeskAppModel`, with the core's packages from [its README](../core/README.md).

Every push that touches `apple/` runs the **Apple app** workflow. It tests the model on Linux and macOS.

## Sign-in apps

Gmail, Google Tasks and Slack sign in with an OAuth app of your own, whose client ID the core reads from `SILENTDESK_GOOGLE_CLIENT_ID`, `SILENTDESK_GOOGLE_CLIENT_SECRET` and `SILENTDESK_SLACK_CLIENT_ID` ([spec/cli.md](../../spec/cli.md)). An app opened from the Finder gets no shell variables, so it also reads them from its defaults:

```sh
defaults write com.silentdesk.app SILENTDESK_GOOGLE_CLIENT_ID "…apps.googleusercontent.com"
defaults write com.silentdesk.app SILENTDESK_GOOGLE_CLIENT_SECRET "…"
defaults write com.silentdesk.app SILENTDESK_SLACK_CLIENT_ID "…"
```

A variable set in the environment wins over the defaults. Only these and `SILENTDESK_SLACK_REDIRECT_PORT` are read from the defaults; the test variables are read from the environment only.
