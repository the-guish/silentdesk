# Secure macOS Apps

Status: reference · Last updated: 2026-10-25

How the apps in [apple-store-reference-apps.md](apple-store-reference-apps.md) that handle secrets or sensitive data protect them, read in their source. The bar is SilentDesk's own, from [spec/storage.md](../spec/storage.md): the database is a SQLCipher file, and secrets live in the OS credential store. No app meets both. Telegram alone encrypts its database. WireGuard, MeetingBar and Sequel Ace show the credential store side. FSNotes, Rocket.Chat and Starcat each protect part of their data and show the trade-offs that come with it.

**How they were read.** Each repository was cloned at its default branch on 2026-10-25 and searched for SQLCipher, Keychain calls, CryptoKit, CommonCrypto, RNCryptor, Electron `safeStorage`, file protection and the pasteboard concealment types. Telegram's storage code lives in [TelegramMessenger/Telegram-iOS](https://github.com/TelegramMessenger/Telegram-iOS) and reaches the macOS app as a submodule. Paths below are inside each app's repository.

## At a glance

| App | Data at rest | Secrets | Take from it |
|---|---|---|---|
| Telegram | SQLCipher, raw key | Key file at the account root, wrapped by the passcode when one is set | Database setup |
| WireGuard | Nothing outside the Keychain | Keychain, this device only, with an access list | Keychain attributes |
| MeetingBar | Preferences | Keychain, one item for the OAuth state | The smallest workable wrapper |
| Sequel Ace | Query history in plain SQLite | Keychain, through one wrapper | Changing Keychain APIs without losing items |
| FSNotes | Notes encrypted one by one, on request | Master password in the Keychain; Git and SFTP credentials in UserDefaults | Per-file encryption with a master password |
| Rocket.Chat | Session tokens in localStorage | Outlook credentials through `safeStorage`, plain text when it is unavailable | Behaviour when the secure store is unavailable |
| Starcat | Plain SQLite | AES-GCM file under a key derived from the machine | The trade-off behind avoiding Keychain prompts |
| Clipbara, Pesty, Flycut | Plain store with CloudKit sync | None | Skipping concealed pasteboard items |
| Pi Stats, Plug | Preferences | One API token in the Keychain | The simplest case |

## Telegram

Repo: [TelegramMessenger/Telegram-macOS](https://github.com/TelegramMessenger/Telegram-macOS). Storage: `submodules/Postbox/Sources/SqliteValueBox.swift` in Telegram-iOS, with SQLCipher built from `submodules/sqlcipher`.

**Database.**
- The database is opened with a raw key, `PRAGMA key="x'<hex>'"`, so no passphrase derivation runs on open. This is the approach in SilentDesk's spec.
- Before the key, `PRAGMA cipher_plaintext_header_size=32` and `cipher_default_plaintext_header_size=32` leave the first 32 bytes of the file in plain text. SQLCipher documents this for WAL-mode databases in shared containers, where the system has to recognise the file as SQLite. The header reveals that it is a SQLite file and its page size, nothing from the tables.
- When the file cannot be opened and `removeDatabaseOnError` is set, `recreateEncryptedDatabase` deletes the file set, including `-wal`, `-shm` and `-open-failures`, and creates an empty database with the same key. Telegram can afford this because the server holds the data. SilentDesk's spec does the opposite and refuses to open, because personal notes exist only locally.

**Key.**
- `Telegram-Mac/app/AppDelegate.swift` builds `ValueBoxEncryptionParameters(forceEncryptionIfNoSet: true, key: …)`, so a database that was created without encryption is encrypted on the next open.
- The key comes from `AppEncryptionParameters(path:)`, kept at the account root. When the user sets a passcode, `applyPasscode` wraps the key with it and the account manager asks for the passcode before the database opens (`PostboxAccessChallengeData.plaintextPassword` in `Telegram-Mac/account/AccountManagerSetup.swift`; the entry flow is in `packages/PasscodeUI/Sources/PasscodeUI/PasscodeLockController.swift`). The class that stores the key was not fetched, so its protection without a passcode is unverified.

**Secrets.** Postbox keeps a `KeychainTable` inside the encrypted database (`Postbox.swift`, `setKeychainEntry`), so the account's own keys are rows, not Keychain items. SilentDesk's spec keeps secrets out of the database on purpose; Telegram shows the other choice.

## WireGuard

Repo: [WireGuard/wireguard-apple](https://github.com/WireGuard/wireguard-apple), `Sources/Shared/Keychain.swift`.

- The whole tunnel configuration, private key included, is the value of one generic-password item. `kSecAttrService` is the bundle identifier with the `.network-extension` suffix removed, so the app and its extension address the same items. `kSecAttrAccount` is the tunnel name plus a UUID, `kSecAttrLabel` is "WireGuard Tunnel: name" and `kSecAttrDescription` is "wg-quick(8) config", which is what the user sees in Keychain Access.
- On macOS the item gets `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, `kSecAttrSynchronizable` false, and an access list from `SecAccessCreate` with two trusted applications, the app and `WireGuardNetworkExtension.appex`. Any other process that reads the item triggers a prompt. On iOS the item is in the app group with `kSecAttrAccessibleAfterFirstUnlock`.
- The item is added with `kSecReturnPersistentRef`, and the persistent reference is what the VPN configuration stores (`passwordReference` in `Sources/Shared/Model/NETunnelProviderProtocol+Extension.swift`). The configuration holds no secret. Replacing a tunnel adds the new item first and deletes the old reference after, `deleteReferences(except:)` sweeps orphans, and `verifyReference` checks that a stored reference still resolves.

For SilentDesk: the attribute set to use on every entry under `com.silentdesk.app`, and the pattern of storing a reference wherever another file has to point at a secret.

## MeetingBar

Repo: [leits/MeetingBar](https://github.com/leits/MeetingBar), `MeetingBar/Utilities/Keychain.swift` and `MeetingBar/Calendar/Providers/Google/GoogleCalendarEventStore.swift`.

- The wrapper is about 60 lines: a generic-password item named by `kSecAttrService`, `kSecAttrAccessibleAfterFirstUnlock`, `kSecReturnData` with a match limit of one. Save deletes any existing item and adds, so there is no update path to get wrong. It sets nothing else, so the item gets the default access list, the creating app.
- What goes in is the AppAuth `OIDAuthState`, with the access token, the refresh token and their expiry, archived by `NSKeyedArchiver` with secure coding required and restored with `unarchivedObject(ofClass:)`. Sign-out deletes the item. Archive failures are logged with privacy level `.private`.

For SilentDesk: one item per entry in the spec's table, and this is the minimum that does it correctly.

## Sequel Ace

Repo: [Sequel-Ace/Sequel-Ace](https://github.com/Sequel-Ace/Sequel-Ace), `Source/Other/Keychain/SAKeychain.swift`.

- The class is the `SecItem*` replacement for the legacy `SecKeychain*` code. It deliberately never passes `kSecUseDataProtectionKeychain`, so it keeps operating on the file-based login keychain where every item from earlier versions already is, and nothing migrates. Its header comment lists the behaviours it pins: add is a silent no-op when the item exists, update recovers from a missing source and from an occupied destination, `SecItemUpdate` keeps the existing access list so legacy items keep working, and delete and update first pin the single matched item through its persistent reference, because an attribute query would hit every match across the keychain search list.
- What goes in: MySQL passwords, SSH passwords and key passphrases (`Source/Other/SSHTunnel/`), Vault OIDC tokens (`Source/Other/Vault/VaultOIDCHandler.swift`) and AWS IAM credentials (`Source/Other/AWS/AWSIAMAuthManager.swift`). Saved connections carry a keychain id, `kcid`, not the password.
- Query history is kept in SQLite through FMDB (`Source/Controllers/SubviewControllers/SPQueryController.m`). Queries can carry literals; for SilentDesk, principle 1 puts data of that kind in the encrypted database.

For SilentDesk: a worked example of changing Keychain code without losing items, which matters once the Swift core has shipped entries and the access API or signing changes. The rule to pin one item by persistent reference before deleting or updating is worth copying as is.

## FSNotes

Repo: [glushchenko/fsnotes](https://github.com/glushchenko/fsnotes), `FSNotesCore/Business/Note.swift`, `FSNotesCore/KeychainPasswordItem.swift`, `FSNotesCore/UserDefaultsManagement.swift`.

- A note is encrypted on request: `writeEncrypted` zips the note's TextBundle into a TextPack and encrypts it with `RNCryptor.encrypt(data:withPassword:)` into one `.etp` file. RNCryptor's password mode is its v3 format: a key derived with PBKDF2, AES-256 in CBC mode and an HMAC over the result.
- The password is the note's own, or the master password read from a Keychain item with service `KeychainConfiguration.serviceName` and account "Master Password".
- `unLock` decrypts into a temporary directory and keeps the TextBundle there while the note is open, so an open note is on disk in plain text, like any unencrypted note, and the password stays on the note object until it is locked again.
- Git and SFTP credentials are kept in UserDefaults: `gitPassword`, `gitPassphrase`, `gitPrivateKeyData`, `sftpPassword` and `sftpPassphrase`.

For SilentDesk: a working pattern of a master secret in the Keychain plus file encryption, if the apps ever keep files outside the database, and the reasons the spec chose whole-database encryption instead: no plaintext temporaries, and one place for every credential.

## Rocket.Chat

Repo: [RocketChat/Rocket.Chat.Electron](https://github.com/RocketChat/Rocket.Chat.Electron), `src/outlookCalendar/ipc.ts`.

- The Outlook login and password are encrypted with Electron `safeStorage.encryptString`, encoded as base64 and stored with the server record in the app's persisted state. On macOS `safeStorage` keeps its key in the Keychain, so the result is Keychain-backed without any `SecItem` code.
- When `safeStorage.isEncryptionAvailable()` is false, the credentials are stored in plain text with a warning in the log. On read, values that do not look like base64 are treated as plain text from earlier versions and used as they are. Both cases are logged rather than shown to the user.
- The session tokens for each server, `Meteor.loginToken`, live in the web view's localStorage, which Chromium keeps on disk unencrypted.

For SilentDesk: principle 1 rules out a plain-text fallback, so a core that cannot reach the credential store fails with error kind `storage` instead.

## Starcat

Repo: [starcat-app/Starcat](https://github.com/starcat-app/Starcat).

- The README and the reference list say Keychain. The header of `Starcat/Core/Keychain/KeychainManager.swift` says that since 2026-06-01 the class, which kept its name, writes a `credentials.json` next to the database instead. The reason given is that ad-hoc signed development builds under the App Sandbox kept triggering Keychain password prompts.
- The file holds the GitHub token, a GitHub App credential, AI API keys per provider and service API keys, as one JSON object encrypted with AES-GCM (`Starcat/Shared/Utilities/CryptoManager.swift`). The key is derived with HKDF-SHA256 from the hardware UUID (`IOPlatformUUID`) and the fixed salt `Starcat-Crypto-Salt-2026` in the source, with the bundle identifier as key material if the UUID is unavailable. The UUID and the salt are both readable on the machine, so the encryption protects the file when it is copied elsewhere, such as into a backup, rather than against other software on the same Mac.
- The file is written atomically, set to mode 0600 and excluded from backup. If decryption fails, the loader reads the file as plain JSON, so files from before the change still load.
- The GRDB database is plain SQLite (`Starcat/Core/Database/DatabaseManager.swift`). The SQLCipher mention in the code is a GitHub URL in a test fixture (`StarcatTests/AgentProductRuntimeTests.swift`).
- The Keychain still holds the MCP server's TLS certificate and private key (`Starcat/Features/MCP/StarcatMCPTLSIdentityStore.swift`).

For SilentDesk: the spec's random key in the credential store also protects against other software on the same machine, which is the property principle 1 asks for and which a key derived from machine identity cannot give. The prompt problem Starcat worked around is real: Keychain items are tied to the signing identity that created them, so the Swift core's signing and entitlements need settling before the first item is written.

## Clipboard managers

[mobrava/Clipbara](https://github.com/mobrava/Clipbara), [momenbasel/pesty](https://github.com/momenbasel/pesty) and [TermiT/flycut](https://github.com/TermiT/flycut) keep their history unencrypted, in SwiftData, in files and in preferences, each with CloudKit sync. Their protection is to never capture secrets in the first place.

- `Clipbara/Services/ContentTypeClassifier.swift` returns nothing when the pasteboard carries `org.nspasteboard.TransientType`, `ConcealedType` or `AutoGeneratedType`, the types password managers set. Pesty does the same in `Sources/Pesty/Monitor/ClipboardMonitor.swift`. Flycut's list in `FlycutOperator.m` adds `PasswordPboardType` and 1Password's own type.
- Clipbara writes one snapshot file with `completeFileProtectionUntilFirstUserAuthentication`, which has an effect only on iOS.

For SilentDesk: relevant only if the apps ever read the clipboard. Then this filter is the minimum.

## Pi Stats and Plug

[Bunn/PiStats](https://github.com/Bunn/PiStats) keeps the Pi-hole API token in the Keychain through a copy of Apple's `KeychainPasswordItem` sample (`Shared/KeyChainPasswordItem.swift`). [wulkano/Plug](https://github.com/wulkano/Plug) keeps the Hype Machine token through the vendored SSKeychain (`Plug/Authentication.swift`). Neither stores anything else sensitive; they are the simplest case of the pattern.
