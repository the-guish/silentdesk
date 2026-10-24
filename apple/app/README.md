# SilentDesk for macOS

Deferred until a Mac is available.

The plan:

- One Xcode project with a macOS target, and an iOS target if one is made. Both share their SwiftUI views.
- It depends on [`../core`](../core) as a local Swift package and uses only the `SilentDeskCore` library.
- Platform services stay here, not in the core: the Keychain for secrets, `ASWebAuthenticationSession` for sign-in, and on iOS, `BGTaskScheduler` for syncing in the background.
