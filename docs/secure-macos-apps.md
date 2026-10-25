# Secure macOS Apps

Status: reference · Last updated: 2026-10-25

How the apps in [apple-store-reference-apps.md](apple-store-reference-apps.md) that handle secrets or sensitive data protect them, read in their source. The bar is SilentDesk's own, from [spec/storage.md](../spec/storage.md): the database is a SQLCipher file, and secrets live in the OS credential store. No app meets both. Telegram alone encrypts its database. WireGuard, MeetingBar and Sequel Ace show the credential store side. FSNotes, Rocket.Chat and Starcat each protect part of their data and show the trade-offs that come with it.

**How they were read.** Each repository was cloned at its default branch on 2026-10-25 and searched for SQLCipher, Keychain calls, CryptoKit, CommonCrypto, RNCryptor, Electron `safeStorage`, file protection and the pasteboard concealment types. Telegram's storage code lives in [TelegramMessenger/Telegram-iOS](https://github.com/TelegramMessenger/Telegram-iOS) and reaches the macOS app as a submodule. Paths below are inside each app's repository. Each section ends with a note in two parts: what is worth taking for SilentDesk, and which of the app's patterns do not fit this project, with the principle or spec line that rules them out.

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
- The database is opened with a raw key, `PRAGMA key="x'<hex>'"`, so no passphrase derivation runs on open.
- Before the key, `PRAGMA cipher_plaintext_header_size=32` and `cipher_default_plaintext_header_size=32` leave the first 32 bytes of the file in plain text. SQLCipher documents this for WAL-mode databases in shared containers, where the system has to recognise the file as SQLite. The header reveals that it is a SQLite file and its page size, nothing from the tables.
- When the file cannot be opened and `removeDatabaseOnError` is set, `recreateEncryptedDatabase` deletes the file set, including `-wal`, `-shm` and `-open-failures`, and creates an empty database with the same key. The server holds the data, so a fresh local database costs a re-sync.

**Key.**
- `Telegram-Mac/app/AppDelegate.swift` builds `ValueBoxEncryptionParameters(forceEncryptionIfNoSet: true, key: …)`, so a database that was created without encryption is encrypted on the next open.
- The key comes from `AppEncryptionParameters(path:)`, kept at the account root. When the user sets a passcode, `applyPasscode` wraps the key with it and the account manager asks for the passcode before the database opens (`PostboxAccessChallengeData.plaintextPassword` in `Telegram-Mac/account/AccountManagerSetup.swift`; the entry flow is in `packages/PasscodeUI/Sources/PasscodeUI/PasscodeLockController.swift`). The class that stores the key was not fetched, so its protection without a passcode is unverified.

**Secrets.** Postbox keeps a `KeychainTable` inside the encrypted database (`Postbox.swift`, `setKeychainEntry`), so the account's own keys are rows, not Keychain items.

**For SilentDesk.**
- Worth taking: whole-file SQLCipher encryption opened with a raw key, which is what the spec describes, and `forceEncryptionIfNoSet` as the shape of a one-way migration if a plain database ever has to be encrypted in place. The plaintext-header pragmas are needed only for WAL databases in shared containers, so they can be left out until the database moves to one.
- Not for SilentDesk: deleting and recreating the database when it fails to open, because personal notes exist only locally and the spec refuses to open instead; the key in a file beside the data, with or without a passcode, because the spec keeps it in the credential store; and secrets as rows inside the database, because the spec keeps every credential in the credential store so a copy of the database carries none.

## WireGuard

Repo: [WireGuard/wireguard-apple](https://github.com/WireGuard/wireguard-apple), `Sources/Shared/Keychain.swift`.

- The whole tunnel configuration, private key included, is the value of one generic-password item. `kSecAttrService` is the bundle identifier with the `.network-extension` suffix removed, so the app and its extension address the same items. `kSecAttrAccount` is the tunnel name plus a UUID, `kSecAttrLabel` is "WireGuard Tunnel: name" and `kSecAttrDescription` is "wg-quick(8) config", which is what the user sees in Keychain Access.
- On macOS the item gets `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, `kSecAttrSynchronizable` false, and an access list from `SecAccessCreate` with two trusted applications, the app and `WireGuardNetworkExtension.appex`. Any other process that reads the item triggers a prompt. On iOS the item is in the app group with `kSecAttrAccessibleAfterFirstUnlock`.
- The item is added with `kSecReturnPersistentRef`, and the persistent reference is what the VPN configuration stores (`passwordReference` in `Sources/Shared/Model/NETunnelProviderProtocol+Extension.swift`). The configuration holds no secret. Replacing a tunnel adds the new item first and deletes the old reference after, `deleteReferences(except:)` sweeps orphans, and `verifyReference` checks that a stored reference still resolves.

**For SilentDesk.**
- Worth taking: the macOS attribute set for every entry under `com.silentdesk.app`, this device only, never synchronised, with a label and description the user can recognise in Keychain Access; an access list that names only the app; and persistent references, with an orphan sweep and a verify step, wherever another file has to point at a secret.
- Not for SilentDesk: a whole configuration file as the item's value. The spec's entries are single tokens and one key, and everything else lives in the encrypted database. The iOS branch, an app group with `AfterFirstUnlock`, has no counterpart here: there is no extension to share with.

## MeetingBar

Repo: [leits/MeetingBar](https://github.com/leits/MeetingBar), `MeetingBar/Utilities/Keychain.swift` and `MeetingBar/Calendar/Providers/Google/GoogleCalendarEventStore.swift`.

- The wrapper is about 60 lines: a generic-password item named by `kSecAttrService`, `kSecAttrAccessibleAfterFirstUnlock`, `kSecReturnData` with a match limit of one. Save deletes any existing item and adds, so there is no update path to get wrong. It sets nothing else, so the item gets the default access list, the creating app.
- What goes in is the AppAuth `OIDAuthState`, with the access token, the refresh token and their expiry, archived by `NSKeyedArchiver` with secure coding required and restored with `unarchivedObject(ofClass:)`. Sign-out deletes the item. Archive failures are logged with privacy level `.private`.

**For SilentDesk.**
- Worth taking: one item per entry in the spec's table, saved by delete-then-add so there is no update path, and a structured credential archived with secure coding rather than concatenated into a string. This is the smallest wrapper that does the job.
- Not for SilentDesk: the default access attributes. The spec's entries should carry WireGuard's set, so they never synchronise and stay on this device. Also the stored access token with its expiry: the spec stores only the refresh token for Google services and obtains access tokens when it needs them.

## Sequel Ace

Repo: [Sequel-Ace/Sequel-Ace](https://github.com/Sequel-Ace/Sequel-Ace), `Source/Other/Keychain/SAKeychain.swift`.

- The class is the `SecItem*` replacement for the legacy `SecKeychain*` code. It deliberately never passes `kSecUseDataProtectionKeychain`, so it keeps operating on the file-based login keychain where every item from earlier versions already is, and nothing migrates. Its header comment lists the behaviours it pins: add is a silent no-op when the item exists, update recovers from a missing source and from an occupied destination, `SecItemUpdate` keeps the existing access list so legacy items keep working, and delete and update first pin the single matched item through its persistent reference, because an attribute query would hit every match across the keychain search list.
- What goes in: MySQL passwords, SSH passwords and key passphrases (`Source/Other/SSHTunnel/`), Vault OIDC tokens (`Source/Other/Vault/VaultOIDCHandler.swift`) and AWS IAM credentials (`Source/Other/AWS/AWSIAMAuthManager.swift`). Saved connections carry a keychain id, `kcid`, not the password.
- Query history is kept in SQLite through FMDB (`Source/Controllers/SubviewControllers/SPQueryController.m`). Queries can carry literals; for SilentDesk, principle 1 puts data of that kind in the encrypted database.

**For SilentDesk.**
- Worth taking: pinning the one matched item by persistent reference before deleting or updating it, the recovery rules for update, and the practice of characterising the old behaviour in tests before replacing Keychain code. All of it matters once the Swift core has shipped entries and the API or the signing changes.
- Not for SilentDesk: staying on the file-based login keychain and preserving legacy access lists. There are no legacy items to keep, so the compatibility constraints do not apply. Also history or any other derived data in a plain SQLite file: principle 1 puts every local table in the encrypted database.

## FSNotes

Repo: [glushchenko/fsnotes](https://github.com/glushchenko/fsnotes), `FSNotesCore/Business/Note.swift`, `FSNotesCore/KeychainPasswordItem.swift`, `FSNotesCore/UserDefaultsManagement.swift`.

- A note is encrypted on request: `writeEncrypted` zips the note's TextBundle into a TextPack and encrypts it with `RNCryptor.encrypt(data:withPassword:)` into one `.etp` file. RNCryptor's password mode is its v3 format: a key derived with PBKDF2, AES-256 in CBC mode and an HMAC over the result.
- The password is the note's own, or the master password read from a Keychain item with service `KeychainConfiguration.serviceName` and account "Master Password".
- `unLock` decrypts into a temporary directory and keeps the TextBundle there while the note is open, so an open note is on disk in plain text, like any unencrypted note, and the password stays on the note object until it is locked again.
- Git and SFTP credentials are kept in UserDefaults: `gitPassword`, `gitPassphrase`, `gitPrivateKeyData`, `sftpPassword` and `sftpPassphrase`.

**For SilentDesk.**
- Worth taking: a master secret in the Keychain that unlocks encrypted files, if the apps ever keep files outside the database, and the user-facing idea that a single item can be locked on demand.
- Not for SilentDesk: encryption one item at a time, with the open item decrypted to a temporary file. The spec chose whole-database encryption so nothing is ever on disk in plain text, notes included. A key derived from a password on every open: the spec uses a random raw key. And credentials in UserDefaults: every secret is an entry in the credential store, none in preferences.

## Rocket.Chat

Repo: [RocketChat/Rocket.Chat.Electron](https://github.com/RocketChat/Rocket.Chat.Electron), `src/outlookCalendar/ipc.ts`.

- The Outlook login and password are encrypted with Electron `safeStorage.encryptString`, encoded as base64 and stored with the server record in the app's persisted state. On macOS `safeStorage` keeps its key in the Keychain, so the result is Keychain-backed without any `SecItem` code.
- When `safeStorage.isEncryptionAvailable()` is false, the credentials are stored in plain text with a warning in the log. On read, values that do not look like base64 are treated as plain text from earlier versions and used as they are. Both cases are logged rather than shown to the user.
- The session tokens for each server, `Meteor.loginToken`, live in the web view's localStorage, which Chromium keeps on disk unencrypted.

**For SilentDesk.**
- Worth taking: reaching the platform's secure store through a thin, standard layer rather than app-specific cryptography. The cores do the same with the Security framework and the Secret Service API.
- Not for SilentDesk: a plain-text fallback when the secure store is unavailable. Principle 1 rules it out, so a core that cannot reach the credential store fails with error kind `storage`. Accepting plain-text values from earlier versions on read: the only plain-text path is the test keyring, and only tests may set it. Session tokens in web storage or any other plain store: tokens are credential-store entries.

## Starcat

Repo: [starcat-app/Starcat](https://github.com/starcat-app/Starcat).

- The README and the reference list say Keychain. The header of `Starcat/Core/Keychain/KeychainManager.swift` says that since 2026-06-01 the class, which kept its name, writes a `credentials.json` next to the database instead. The reason given is that ad-hoc signed development builds under the App Sandbox kept triggering Keychain password prompts.
- The file holds the GitHub token, a GitHub App credential, AI API keys per provider and service API keys, as one JSON object encrypted with AES-GCM (`Starcat/Shared/Utilities/CryptoManager.swift`). The key is derived with HKDF-SHA256 from the hardware UUID (`IOPlatformUUID`) and the fixed salt `Starcat-Crypto-Salt-2026` in the source, with the bundle identifier as key material if the UUID is unavailable. The UUID and the salt are both readable on the machine, so the encryption protects the file when it is copied elsewhere, such as into a backup, rather than against other software on the same Mac.
- The file is written atomically, set to mode 0600 and excluded from backup. If decryption fails, the loader reads the file as plain JSON, so files from before the change still load.
- The GRDB database is plain SQLite (`Starcat/Core/Database/DatabaseManager.swift`). The SQLCipher mention in the code is a GitHub URL in a test fixture (`StarcatTests/AgentProductRuntimeTests.swift`).
- The Keychain still holds the MCP server's TLS certificate and private key (`Starcat/Features/MCP/StarcatMCPTLSIdentityStore.swift`).

**For SilentDesk.**
- Worth taking: the file hygiene, mode 0600, atomic writes and exclusion from backup, which the spec's data folder should match; the self-check canary that proves the store round-trips before the first real write; separate entries for credentials that fail independently, so revoking one never signs the user out of another, which the spec's one-entry-per-service table already does; and the lesson behind the change. Keychain items are tied to the signing identity that created them, so the Swift core's signing and entitlements need settling before the first item is written, or development builds will prompt.
- Not for SilentDesk: a key derived from machine identity. Principle 1 asks for protection against other software on the same machine, which only a random key in the credential store gives. A credentials file beside the database: the spec keeps secrets in the credential store. Reading a plain file when decryption fails: no plain-text path outside tests. And a plain database: the database is a SQLCipher file.

## Clipboard managers

[mobrava/Clipbara](https://github.com/mobrava/Clipbara), [momenbasel/pesty](https://github.com/momenbasel/pesty) and [TermiT/flycut](https://github.com/TermiT/flycut) keep their history unencrypted, in SwiftData, in files and in preferences, each with CloudKit sync. Their protection is to never capture secrets in the first place.

- `Clipbara/Services/ContentTypeClassifier.swift` returns nothing when the pasteboard carries `org.nspasteboard.TransientType`, `ConcealedType` or `AutoGeneratedType`, the types password managers set. Pesty does the same in `Sources/Pesty/Monitor/ClipboardMonitor.swift`. Flycut's list in `FlycutOperator.m` adds `PasswordPboardType` and 1Password's own type.
- Clipbara writes one snapshot file with `completeFileProtectionUntilFirstUserAuthentication`, which has an effect only on iOS.

**For SilentDesk.**
- Worth taking: the concealment filter, if the apps ever read the clipboard, and the habit behind it: do not capture what the product does not need, which is principle 4.
- Not for SilentDesk: an unencrypted local history, and syncing it through CloudKit. Local data is encrypted under principle 1, and personal notes are never synced under principle 5.

## Pi Stats and Plug

[Bunn/PiStats](https://github.com/Bunn/PiStats) keeps the Pi-hole API token in the Keychain through a copy of Apple's `KeychainPasswordItem` sample (`Shared/KeyChainPasswordItem.swift`). [wulkano/Plug](https://github.com/wulkano/Plug) keeps the Hype Machine token through the vendored SSKeychain (`Plug/Authentication.swift`). Neither stores anything else sensitive; they are the simplest case of the pattern.

**For SilentDesk.**
- Worth taking: Apple's sample as a starting point for a wrapper, if one is wanted. One token per item needs no more than that.
- Not for SilentDesk: a vendored third-party Keychain wrapper. The spec's single service name needs a handful of Security framework calls, and the Python core goes through the `keyring` library's Secret Service backend, so neither core needs a dependency for it.
