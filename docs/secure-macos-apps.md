# Secure macOS Apps

Status: reference · Last updated: 2026-10-25

How the open-source apps in [apple-store-reference-apps.md](apple-store-reference-apps.md) protect sensitive data, checked in each app's source. The bar is SilentDesk's own, from [spec/storage.md](../spec/storage.md): the database is a SQLCipher file, and secrets live in the OS credential store.

**How they were checked.**
- 23 of the 55 repositories were cloned at their default branch on 2026-10-25: every app whose entry mentions a database, the Keychain, CloudKit, credentials or clipboard capture. Their code was searched for SQLCipher, Keychain calls (`SecItem*` and wrappers), CryptoKit, CommonCrypto, RNCryptor, Electron `safeStorage`, file protection and the pasteboard concealment types.
- Telegram keeps its storage code in [TelegramMessenger/Telegram-iOS](https://github.com/TelegramMessenger/Telegram-iOS), pulled into the macOS app as a submodule. That repository was checked too.
- The other 32 apps store preferences and files and hold no secrets; they were judged from the reference list alone. Krita and LibreOffice were not cloned: they keep no user secrets.

## Summary

| Protection | Apps |
|---|---|
| Encrypted database | 1: Telegram |
| Secrets in the Keychain, data in plain files | 5: WireGuard, MeetingBar, Sequel Ace, Pi Stats, Plug |
| Partial: some secrets protected, others in plain text | 3: FSNotes, Rocket.Chat, Starcat |
| No encryption, but password-manager content is skipped | 3: Clipbara, Pesty, Flycut |
| Keychain used for something other than user secrets | 4: Nightwatch, Podlive, Seahorse Studio, UTM |
| Nothing protected, or nothing sensitive stored | 39 |

No app meets SilentDesk's bar. Telegram is the only one with an encrypted database, and it does not keep the key in the credential store. WireGuard and MeetingBar show the Keychain side done well.

## Worth copying

### Telegram: the database
- Repos: [TelegramMessenger/Telegram-macOS](https://github.com/TelegramMessenger/Telegram-macOS); storage in Telegram-iOS, `submodules/Postbox/Sources/SqliteValueBox.swift`, with SQLCipher in `submodules/sqlcipher`
- The Postbox database is opened with a raw key, `PRAGMA key="x'…'"`, and `PRAGMA cipher_plaintext_header_size=32`, which leaves the file's SQLite header readable.
- The key comes from `AppEncryptionParameters` at the account root path. When the user sets a passcode, the key is wrapped with it (`applyPasscode` in `packages/PasscodeUI/Sources/PasscodeUI/PasscodeLockController.swift`). The class that stores the unwrapped key is in a dependency that was not fetched, so its protection without a passcode is unverified.
- For SilentDesk: the closest model. The raw-key approach is the spec's; the spec keeps the key in the credential store instead.

### WireGuard: Keychain attributes
- Repo: [WireGuard/wireguard-apple](https://github.com/WireGuard/wireguard-apple), `Sources/Shared/Keychain.swift`
- Tunnel configurations, private keys included, are generic-password items. On macOS they get `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, `kSecAttrSynchronizable` false, and an access list (`SecAccessCreate`) that admits only the app and its network extension. The VPN configuration keeps a persistent reference to the item, not the value.
- For SilentDesk: the attributes to set on every entry under `com.silentdesk.app`.

### MeetingBar: OAuth tokens
- Repo: [leits/MeetingBar](https://github.com/leits/MeetingBar), `MeetingBar/Utilities/Keychain.swift` and `MeetingBar/Calendar/Providers/Google/GoogleCalendarEventStore.swift`
- The Google `OIDAuthState` is archived with secure coding into one Keychain item, through a small wrapper that saves, loads and deletes.
- For SilentDesk: a template for the Gmail and Google Tasks refresh tokens.

### Sequel Ace: many kinds of credential
- Repo: [Sequel-Ace/Sequel-Ace](https://github.com/Sequel-Ace/Sequel-Ace), `Source/Other/Keychain/SAKeychain.swift`
- MySQL passwords, SSH passwords and key passphrases, Vault OIDC tokens and AWS IAM credentials all go through one `SecItem*` wrapper. Query history, which can carry data, is plain SQLite through FMDB (`Source/Controllers/SubviewControllers/SPQueryController.m`).
- For SilentDesk: good for secrets. The history is the kind of data principle 1 forbids in plain text.

### Pi Stats and Plug: one token each
- [Bunn/PiStats](https://github.com/Bunn/PiStats) keeps the Pi-hole API token in the Keychain (`Shared/KeyChainPasswordItem.swift`). [wulkano/Plug](https://github.com/wulkano/Plug) keeps the Hype Machine token through SSKeychain (`Plug/Authentication.swift`). Neither stores anything else sensitive.

## Partial

### FSNotes
- Repo: [glushchenko/fsnotes](https://github.com/glushchenko/fsnotes)
- Notes can be encrypted one by one with RNCryptor's password format into `.etp` files (`FSNotesCore/Business/Note.swift`). The master password is a Keychain item (`FSNotesCore/KeychainPasswordItem.swift`).
- Git and SFTP passwords, key passphrases and private keys are UserDefaults values in plain text: `gitPassword`, `gitPassphrase`, `gitPrivateKeyData`, `sftpPassword` and `sftpPassphrase` in `FSNotesCore/UserDefaultsManagement.swift`.

### Rocket.Chat
- Repo: [RocketChat/Rocket.Chat.Electron](https://github.com/RocketChat/Rocket.Chat.Electron), `src/outlookCalendar/ipc.ts`
- Outlook login and password are encrypted with Electron `safeStorage`, which uses the Keychain on macOS. When `isEncryptionAvailable()` is false they are stored in plain text, with a warning in the log.
- Server session tokens (`Meteor.loginToken`) live in the web view's localStorage, unencrypted on disk.

### Starcat
- Repo: [starcat-app/Starcat](https://github.com/starcat-app/Starcat)
- The README and the reference list say Keychain. Since 2026-06-01 (`Starcat/Core/Keychain/KeychainManager.swift`), GitHub tokens and AI API keys live in `credentials.json` next to the database, encrypted with AES-GCM. The key is derived with HKDF from the hardware UUID and a fixed salt in the source (`Starcat/Shared/Utilities/CryptoManager.swift`), so any local process can derive it. The move was made to stop Keychain password prompts under ad-hoc signing with the App Sandbox.
- The GRDB database is plain SQLite (`Starcat/Core/Database/DatabaseManager.swift`). The SQLCipher mention in the reference list is a GitHub URL in a test fixture (`StarcatTests/AgentProductRuntimeTests.swift`).
- The Keychain still holds the MCP server's TLS identity (`Starcat/Features/MCP/StarcatMCPTLSIdentityStore.swift`).
- For SilentDesk: a warning. A key derived from machine identity is obfuscation, not encryption. The prompt problem it worked around is real in development builds and worth testing early.

## Clipboard managers: skip, rather than encrypt

[mobrava/Clipbara](https://github.com/mobrava/Clipbara), [momenbasel/pesty](https://github.com/momenbasel/pesty) and [TermiT/flycut](https://github.com/TermiT/flycut) store their history unencrypted: SwiftData, files and preferences, each with CloudKit sync. All three ignore pasteboard items marked `org.nspasteboard.ConcealedType`, `TransientType` or `AutoGeneratedType`, and Flycut also `PasswordPboardType` and 1Password's own type, so password managers' content is never stored. Clipbara writes one snapshot with `completeFileProtectionUntilFirstUserAuthentication`, which only matters on iOS. Relevant to SilentDesk only if it ever reads the clipboard.

## Keychain, but not for user secrets

The reference list counts 13 Keychain apps. In four of them the item is not a user secret:
- Nightwatch: Keychain only in a release script (`scripts/review-status.swift`). The app stores no secrets.
- Podlive: Keychain only inside the vendored Parse SDK (`App/Carthage/Checkouts`), which keeps its own session token there.
- Seahorse Studio: the item is a purchase flag (`Seashore/source/application/SeaSupport.m`, service `purchases`).
- UTM: the item is the UTM Remote TLS identity (`Remote/UTMRemoteKeyManager.swift`). The SPICE server password is a field of the VM configuration (`Configuration/UTMQemuConfigurationQEMU.swift`).

## Nothing protected

- Medis keeps Redis connection favorites in localStorage (`src/renderer/storage/Favorites.js`), passwords and SSH key passphrases included.
- KubeContext writes kubeconfig files in plain text (`KubeContext/Utils.swift`), as kubectl does.
- tmpNote, Kiwix, OpenHabitTracker and Notenik use plain Core Data, SQLite or files and hold no secrets.
- Krita and LibreOffice were not checked; they keep no user secrets.
- The remaining apps store preferences and files and hold nothing sensitive.
