# SilentDesk for macOS

The macOS app, in SwiftUI. It reaches the core in [`../core`](../core) through `SilentDeskCore` only, and behaves as the GTK app in [linux/gtk](../../linux/gtk/README.md) does.

It needs macOS 14 or newer. It is a Swift package, not an Xcode project, so it builds with `swift build` and CI can make the app without a Mac.

## How it works

- **The window:** the queue on the left, newest first, with an avatar of who wrote last, its service, and when; a topic whose newest item the user wrote reads "Waiting on others". The search field above it filters by title, service and people. Under it, when topics last changed, and a spinner while a round runs. The open topic is on the right.
- **The topic:** its items, each with who wrote it, whether it was received or sent, and when, and a button to open it in its service; a note says why there is no text. Where the service keeps a conversation (Slack), its recent messages are read live and shown instead, never stored. Gmail topics have a reply box; ⌘↩ sends. A Delete button shows on topics their connector marks deletable, and on each deletable item of a topic with several; each asks first.
- **Services:** in Settings (⌘,). GitHub and Jira connect with a form; Gmail, Google Tasks and Slack sign in through the browser. A service that connects syncs at once; one that disconnects drops its topics, after asking.
- **Syncing:** at startup, every 2 minutes, and when the app comes to the front if the last round started more than 30 seconds ago. **Refresh** (⌘R) starts a round at once. Failures show as a notice at the bottom of the window, and the old topics stay.
- **Menus and shortcuts:** ⌘R refreshes, ⌘F searches, ⌘, opens Services, ⌘⌫ deletes the open topic, ⌘↩ sends a reply, ⌘W closes the window and quits, as the GTK app does.

| Path | What it is |
|------|------------|
| `Sources/SilentDeskAppModel/` | What the windows show and do, without SwiftUI, so it builds and is tested on Linux too |
| `Sources/SilentDeskAppModel/QueueModel.swift` | The queue, search, Refresh and automatic syncing |
| `Sources/SilentDeskAppModel/TopicModel.swift` | The topic screen: items or conversation, reply and delete |
| `Sources/SilentDeskAppModel/ServicesModel.swift` | The Services settings: connect forms and Disconnect |
| `Sources/SilentDeskAppModel/Format.swift`, `Services.swift` | How topics read, and what each service asks for and offers |
| `Sources/SilentDeskAppModel/AppSettings.swift` | The core's settings: the environment, then the app's defaults |
| `Sources/SilentDeskAppModel/DemoDesk.swift` | Made-up topics, for `--demo` and the screenshots |
| `Sources/SilentDesk/` | The SwiftUI app; macOS only |
| `Sources/SilentDesk/ScreenshotTour.swift` | `--screenshots DIR`: saves every screen as a PNG, light and dark, and quits |
| `Bundle/Info.plist` | The app bundle's Info.plist |
| `Scripts/bundle.sh` | Builds `SilentDesk.app`: universal, release, signed ad hoc |
| `Scripts/make-icon.swift` | Draws the app's icon at build time |

## Build

On a Mac with Xcode 16 or newer:

```sh
swift test                      # from this folder
swift run SilentDesk --demo     # the app over made-up topics
Scripts/bundle.sh               # .build/SilentDesk.app
```

On Linux, `swift test` builds and tests `SilentDeskAppModel`, with the core's packages from [its README](../core/README.md).

Every push that touches `apple/` runs the **Apple app** workflow. It tests the model on Linux and macOS, builds `SilentDesk.app`, and uploads two artifacts: `SilentDesk-macOS`, the app, and `screenshots`, every screen in light and dark.

## Try a build

1. Open the workflow run on GitHub and download `SilentDesk-macOS`.
2. Unzip it, then unzip the `SilentDesk.zip` inside. The inner zip keeps the bundle's symbolic links and signature.
3. The app is signed ad hoc, not with a Developer ID, so macOS blocks it the first time. Clear the download's quarantine:

   ```sh
   xattr -dr com.apple.quarantine SilentDesk.app
   ```

   Or open it, then choose **Open Anyway** in System Settings → Privacy & Security.

Each build has a new signature, so the first time a new build reads its Keychain items, macOS asks whether SilentDesk may use them. **Always Allow** keeps it from asking again until the next build.

## Sign-in apps

Gmail, Google Tasks and Slack sign in with an OAuth app of your own, whose client ID the core reads from `SILENTDESK_GOOGLE_CLIENT_ID`, `SILENTDESK_GOOGLE_CLIENT_SECRET` and `SILENTDESK_SLACK_CLIENT_ID` ([spec/cli.md](../../spec/cli.md)). An app opened from the Finder gets no shell variables, so it also reads them from its defaults:

```sh
defaults write com.silentdesk.app SILENTDESK_GOOGLE_CLIENT_ID "…apps.googleusercontent.com"
defaults write com.silentdesk.app SILENTDESK_GOOGLE_CLIENT_SECRET "…"
defaults write com.silentdesk.app SILENTDESK_SLACK_CLIENT_ID "…"
```

A variable set in the environment wins over the defaults. Only these and `SILENTDESK_SLACK_REDIRECT_PORT` are read from the defaults; the test variables are read from the environment only.

## Platform services

- **Secrets** live in the login Keychain, under the service `com.silentdesk.app`, as the core keeps them.
- **The database** is `~/Library/Application Support/SilentDesk/silentdesk.db`, encrypted with SQLCipher.
- **Sign-in** opens the default browser and listens on the loopback interface for the redirect, as the command line does.
