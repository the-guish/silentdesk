# Apple Store Reference Apps

Status: reference · Last updated: 2026-10-25

Open-source apps confirmed on the Mac App Store, as a reference for publishing SilentDesk there. How the ones that handle secrets protect them is in [secure-macos-apps.md](secure-macos-apps.md).

**How they were found.**
- 48 come from the [open-source-mac-os-apps](https://github.com/serhii-londar/open-source-mac-os-apps) list, keeping those whose README links a Mac App Store listing.
- The other 7 were checked one by one: UTM, Krita, Telegram, WireGuard, Gifski, Hidden Bar and LibreOffice.
- Every listing was confirmed with Apple's iTunes lookup or search API.

**License** comes from the license file in the repository, or from the README when the repository has no license file.

**Languages** are bytes per language in the repository, the way GitHub counts them. A combination lists every language with at least 10% of the code, and smaller shares are in brackets. Vendored code, submodules and build scripts (Shell, Ruby, Perl) are not counted. Code fetched at build time is not counted either.

**Database** comes from searching the code and the dependency manifests for storage APIs and libraries, and **Keychain** from Keychain calls in the app's own code, checked on 2026-10-25 against each repository's default branch. An app counts as using a database when it embeds a database engine: SQLite, directly or through Core Data or SwiftData, or Firebird. "Files" means preferences (`UserDefaults`) and files the app writes itself.

## Summary

| Primary language | Apps |
|---|---|
| Swift | 36 (65%) |
| Objective-C | 10 (18%) |
| JavaScript | 3 (5%) |
| C++ | 2 (4%) |
| TypeScript | 2 (4%) |
| C# | 1 (2%) |
| Rust | 1 (2%) |

| Storage | Apps |
|---|---|
| SQLite, directly | 5 (9%) |
| Core Data or SwiftData, which store in SQLite | 4 (7%) |
| Embedded Firebird | 1 (2%) |
| No database: preferences and files | 38 (69%) |
| No database: Electron or Tauri storage | 4 (7%) |
| No database: CloudKit sync | 2 (4%) |
| Nothing stored | 1 (2%) |

| License | Apps |
|---|---|
| MIT | 33 (60%) |
| GPL-3.0 | 9 (16%) |
| Apache-2.0 | 6 (11%) |
| GPL-2.0 | 4 (7%) |
| BSD-2-Clause | 1 (2%) |
| MPL-2.0 | 1 (2%) |
| Not stated | 1 (2%) |

- **Python:** under 10% in every app. Krita is the only one where we know it ships, as its plugin runtime.
- **Encryption at rest:** Telegram is the only app whose database is encrypted.
- **Keychain:** 7 apps keep user secrets in it: WireGuard, MeetingBar, Sequel Ace, Pi Stats, Plug, FSNotes and Rocket.Chat, the last through Electron's `safeStorage`. Podlive does so through the Parse SDK. Starcat and UTM keep only a TLS identity there, Seahorse Studio a purchase flag, and Nightwatch's only Keychain code is a release script. Telegram's key handling was not read.

## Apps with a database

### Clipbara
- Repo: [mobrava/Clipbara](https://github.com/mobrava/Clipbara)
- App Store: [Clipbara](https://apps.apple.com/app/id6803537696)
- What it does: clipboard manager with pinboards
- License: GPL-3.0
- Languages: Swift
- Architecture: one listing shared with iPhone and iPad
- Database: SwiftData (SQLite), with CloudKit sync

### Kiwix
- Repo: [kiwix/apple](https://github.com/kiwix/apple)
- App Store: [Kiwix](https://apps.apple.com/app/id997079563)
- What it does: offline Wikipedia and other content
- License: GPL-3.0
- Languages: Swift (Objective-C 6%, JavaScript 3%)
- Architecture: reads ZIM content files. One listing shared with iPhone and iPad
- Database: Core Data (SQLite)

### Krita
- Repo: [KDE/krita](https://github.com/KDE/krita)
- App Store: [Krita](https://apps.apple.com/app/id1594607976)
- What it does: digital painting
- License: GPL-3.0
- Languages: C++ (Python 3%)
- Architecture: C++/Qt app that runs Python 3.10 inside it for plugins. The team reports months of work on the sandbox, and the sandbox stops plugins from running `xcrun`
- Database: SQLite through Qt SQL (resource cache)

### LibreOffice
- Repo: [LibreOffice/core](https://github.com/LibreOffice/core)
- App Store: [LibreOffice](https://apps.apple.com/app/id1630474372)
- What it does: office suite
- License: MPL-2.0 (the repo also carries the LGPL-3.0 and GPL-3.0 texts)
- Languages: C++ (Java 6%)
- Architecture: published by The Document Foundation for a fee. The store build leaves Java out
- Database: embedded Firebird for Base (HSQLDB needs Java, so it isn't in the store build)

### OpenHabitTracker
- Repo: [Jinjinov/OpenHabitTracker](https://github.com/Jinjinov/OpenHabitTracker)
- App Store: [OpenHabitTracker](https://apps.apple.com/app/id6654885470)
- What it does: notes, tasks and habit tracking
- License: GPL-3.0
- Languages: C#
- Architecture: .NET app. One listing shared with iPhone and iPad
- Database: SQLite through Entity Framework Core

### Podlive
- Repo: [Podlive/podlive-macos](https://github.com/Podlive/podlive-macos)
- App Store: [Podlive](https://apps.apple.com/app/id1210411572)
- What it does: live-streaming podcast player
- License: MIT (README)
- Languages: Objective-C
- Database: Core Data (SQLite), plus calls to SQLite's C API. Keychain only through the Parse SDK, which keeps its session token there

### Sequel Ace
- Repo: [Sequel-Ace/Sequel-Ace](https://github.com/Sequel-Ace/Sequel-Ace)
- App Store: [Sequel Ace](https://apps.apple.com/app/id1518036000)
- What it does: MySQL and MariaDB client
- License: MIT
- Languages: Objective-C + Swift
- Database: SQLite through FMDB, for query history; Keychain

### Starcat
- Repo: [starcat-app/Starcat](https://github.com/starcat-app/Starcat)
- App Store: [Starcat for GitHub](https://apps.apple.com/app/id6788809803)
- What it does: local-first manager for GitHub stars
- License: MIT
- Languages: JavaScript + Swift
- Database: SQLite through GRDB, not encrypted. Since June 2026 the GitHub token and API keys are in an AES-GCM-encrypted file next to it, not in the Keychain; the Keychain holds only the MCP server's TLS identity. The SQLCipher mention in the code is a URL in a test fixture

### Telegram
- Repo: [TelegramMessenger/Telegram-macOS](https://github.com/TelegramMessenger/Telegram-macOS)
- App Store: [Telegram](https://apps.apple.com/app/id747648890)
- What it does: messaging
- License: GPL-2.0
- Languages: C + Swift (JavaScript 3%, C++ 3%)
- Architecture: its Postbox storage layer runs on SQLite. The source link on macos.telegram.org (overtake/TelegramSwift) is no longer public
- Database: SQLite encrypted with SQLCipher, in the Postbox code that comes from the Telegram-iOS submodule. No Keychain use was found in the macOS app's own sources; the class that keeps the database key was not read

### tmpNote
- Repo: [buddax2/tmpNote](https://github.com/buddax2/tmpNote)
- App Store: [tmpNote](https://apps.apple.com/app/id1293664761)
- What it does: temporary notes
- License: MIT
- Languages: Swift
- Database: Core Data (SQLite), with CloudKit sync

## Apps without a database

### ArtWall
- Repo: [JustinFincher/ASWP-for-macOS](https://github.com/JustinFincher/ASWP-for-macOS)
- App Store: [ArtWall](https://apps.apple.com/app/id1178151992)
- What it does: ArtStation artwork as wallpaper
- License: MIT
- Languages: Objective-C
- Architecture: listed under a different name than the repo
- Database: no, files

### AutoMute
- Repo: [yonilevy/automute](https://github.com/yonilevy/automute)
- App Store: [AutoMute](https://apps.apple.com/app/id1118136179)
- What it does: mutes sound when headphones disconnect or the Mac wakes
- License: MIT
- Languages: C++ + Objective-C
- Database: no, files

### BarTranslate
- Repo: [ThijmenDam/BarTranslate](https://github.com/ThijmenDam/BarTranslate)
- App Store: [BarTranslate](https://apps.apple.com/app/id6759278154)
- What it does: menu bar translator
- License: GPL-3.0
- Languages: Swift
- Database: no, files

### Better Resource Monitor
- Repo: [alexx855/better-resource-monitor](https://github.com/alexx855/better-resource-monitor)
- App Store: [Better Resource Monitor](https://apps.apple.com/app/id6758237306)
- What it does: menu bar CPU, memory, disk, GPU and network monitor
- License: MIT
- Languages: JavaScript + Rust + TypeScript
- Architecture: Tauri v2, sandboxed. Also a DMG on GitHub Releases, without automatic updates
- Database: no, the Tauri store plugin (a JSON file)

### Boop
- Repo: [IvanMathy/Boop](https://github.com/IvanMathy/Boop)
- App Store: [Boop](https://apps.apple.com/app/id1518425043)
- What it does: scriptable scratchpad for developers
- License: MIT
- Languages: JavaScript + Swift
- Database: no, files

### Chord Detector
- Repo: [cemolcay/ChordDetector](https://github.com/cemolcay/ChordDetector)
- App Store: [Chord Detector](https://apps.apple.com/app/id1219549675)
- What it does: menu bar app that detects the chords of the playing song
- License: MIT
- Languages: Swift
- Database: no, files

### Cleaner for Xcode
- Repo: [waylybaye/XcodeCleaner](https://github.com/waylybaye/XcodeCleaner)
- App Store: [Cleaner for Xcode](https://apps.apple.com/app/id1296084683)
- What it does: frees disk space used by Xcode
- License: GPL-3.0
- Languages: JavaScript + Objective-C
- Architecture: React Native for macOS
- Database: no, files

### Core-Monitor
- Repo: [offyotto/Core-Monitor](https://github.com/offyotto/Core-Monitor)
- App Store: [Core-Monitor](https://apps.apple.com/app/id6762558526)
- What it does: system monitor with menu bar stats and fan control
- License: GPL-3.0
- Languages: Swift (Python 2%)
- Database: no, files

### CotEditor
- Repo: [coteditor/CotEditor](https://github.com/coteditor/CotEditor)
- App Store: [CotEditor](https://apps.apple.com/app/id1024640650)
- What it does: plain-text editor
- License: Apache-2.0 (image resources CC BY-NC-ND 4.0)
- Languages: Swift
- Database: no, files

### DiskWise
- Repo: [DreamOfXM/diskwise](https://github.com/DreamOfXM/diskwise)
- App Store: [DiskWise](https://apps.apple.com/app/id6813265402)
- What it does: disk cleaner that moves files to the Trash
- License: Apache-2.0
- Languages: Swift + TypeScript
- Database: no, files

### Equinox
- Repo: [rlxone/Equinox](https://github.com/rlxone/Equinox)
- App Store: [Equinox](https://apps.apple.com/app/id1591510203)
- What it does: creates dynamic wallpapers
- License: MIT
- Languages: Swift
- Database: no, files

### Flycut
- Repo: [TermiT/flycut](https://github.com/TermiT/flycut)
- App Store: [Flycut](https://apps.apple.com/app/id442160987)
- What it does: clipboard manager for developers
- License: not stated in the repo
- Languages: Objective-C (Swift 6%, C 3%)
- Database: no, preferences, with CloudKit sync

### FolderForge
- Repo: [KeplSiv/FolderForge](https://github.com/KeplSiv/FolderForge)
- App Store: [FolderForge](https://apps.apple.com/app/id6799417746)
- What it does: customises folder colours and icons
- License: MIT
- Languages: Swift (Python 2%)
- Database: no, files

### FSNotes
- Repo: [glushchenko/fsnotes](https://github.com/glushchenko/fsnotes)
- App Store: [FSNotes](https://apps.apple.com/app/id1277179284)
- What it does: notes manager in the style of nvALT
- License: MIT
- Languages: JavaScript + Swift
- Architecture: notes are plain Markdown files
- Database: no, Markdown files, each one optionally encrypted; Keychain for the master password

### Gifski
- Repo: [sindresorhus/Gifski](https://github.com/sindresorhus/Gifski)
- App Store: [Gifski](https://apps.apple.com/app/id1351639930)
- What it does: converts videos to GIFs
- License: MIT (the app; the gifski library has its own license)
- Languages: Rust + Swift
- Architecture: Swift app with the Rust gifski encoder in the repo. Also a separate build for people without App Store access
- Database: no, files

### Hidden Bar
- Repo: [dwarvesf/hidden](https://github.com/dwarvesf/hidden)
- App Store: [Hidden Bar](https://apps.apple.com/app/id1452453066)
- What it does: hides menu bar icons
- License: MIT
- Languages: Swift (Objective-C 4%)
- Architecture: also notarised for download outside the store
- Database: no, files

### InjectionIII
- Repo: [johnno1962/InjectionIII](https://github.com/johnno1962/InjectionIII)
- App Store: [InjectionIII](https://apps.apple.com/app/id1380446739)
- What it does: live code injection for Swift development
- License: MIT
- Languages: C + Objective-C + Swift (Java 7%)
- Architecture: listed under a different seller than the repo owner
- Database: no, files

### ItsPaint
- Repo: [joshlin2201/itspaint](https://github.com/joshlin2201/itspaint)
- App Store: [ItsPaint](https://apps.apple.com/app/id6796493980)
- What it does: paint and screenshot markup
- License: MIT
- Languages: Swift
- Database: no, files

### JustMD
- Repo: [yuraist/just-md](https://github.com/yuraist/just-md)
- App Store: [JustMD](https://apps.apple.com/app/id6779422717)
- What it does: Markdown editor with PDF export
- License: MIT
- Languages: Swift (Python 5%, TypeScript 3%)
- Database: no, files

### KubeContext
- Repo: [turkenh/KubeContext](https://github.com/turkenh/KubeContext)
- App Store: [KubeContext](https://apps.apple.com/app/id1438838068)
- What it does: switches Kubernetes contexts
- License: Apache-2.0
- Languages: Swift
- Database: no, files

### Localizable.strings
- Repo: [cristibaluta/Localizable.strings](https://github.com/cristibaluta/Localizable.strings)
- App Store: [Localizable.strings](https://apps.apple.com/app/id1063953896)
- What it does: localises iOS and macOS projects
- License: MIT
- Languages: Swift
- Database: no, files

### LosslessCut
- Repo: [mifi/lossless-cut](https://github.com/mifi/lossless-cut)
- App Store: [LosslessCut](https://apps.apple.com/app/id1505323402)
- What it does: lossless video and audio editing
- License: GPL-2.0
- Languages: TypeScript
- Architecture: Electron
- Database: no, electron-store (a JSON file)

### MacPacker
- Repo: [sarensw/MacPacker](https://github.com/sarensw/MacPacker)
- App Store: [MacPacker](https://apps.apple.com/app/id6473273874)
- What it does: archive manager
- License: GPL-3.0
- Languages: Swift (C++ 6%)
- Database: no, files

### Medis 2
- Repo: [luin/medis](https://github.com/luin/medis)
- App Store: [Medis 2](https://apps.apple.com/app/id1579200037)
- What it does: Redis GUI
- License: MIT
- Languages: JavaScript (TypeScript 7%)
- Architecture: Electron
- Database: no, browser localStorage

### MeetingBar
- Repo: [leits/MeetingBar](https://github.com/leits/MeetingBar)
- App Store: [MeetingBar](https://apps.apple.com/app/id1532419400)
- What it does: menu bar app for calendar meetings
- License: Apache-2.0
- Languages: Swift
- Database: no, files; Keychain

### Menu Bar Percent Calculator
- Repo: [cemolcay/PercentCalculator](https://github.com/cemolcay/PercentCalculator)
- App Store: [Menu Bar Percent Calculator](https://apps.apple.com/app/id1286560999)
- What it does: calculates percentages
- License: MIT
- Languages: Swift
- Database: no, stores nothing

### Nightwatch
- Repo: [rsutcliffe/nightwatch](https://github.com/rsutcliffe/nightwatch)
- App Store: [Nightwatch](https://apps.apple.com/app/id6816390602)
- What it does: clear-sky alerts for amateur astronomers
- License: MIT
- Languages: C + Swift
- Database: no, files. The only Keychain code is a release script, not the app

### Notenik
- Repo: [hbowie/notenik-swift](https://github.com/hbowie/notenik-swift)
- App Store: [Notenik](https://apps.apple.com/app/id1465997984)
- What it does: note-taking
- License: MIT
- Languages: Swift
- Database: no, files

### PageExtender
- Repo: [fphilipe/PageExtender.app](https://github.com/fphilipe/PageExtender.app)
- App Store: [PageExtender](https://apps.apple.com/app/id1457557274)
- What it does: adds your own CSS and JS to web pages
- License: MIT
- Languages: Swift (JavaScript 7%)
- Architecture: Safari extension
- Database: no, files

### Pesty
- Repo: [momenbasel/pesty](https://github.com/momenbasel/pesty)
- App Store: [Pesty](https://apps.apple.com/app/id6784511397)
- What it does: clipboard manager inspired by Paste
- License: MIT
- Languages: Swift
- Architecture: one listing shared with iPhone and iPad
- Database: no, files, with CloudKit sync

### Pi Stats
- Repo: [Bunn/PiStats](https://github.com/Bunn/PiStats)
- App Store: [Pi Stats](https://apps.apple.com/app/id1514075262)
- What it does: shows Pi-hole statistics
- License: BSD-2-Clause
- Languages: Swift
- Database: no, files; Keychain

### PiPifier
- Repo: [arnoappenzeller/PiPifier](https://github.com/arnoappenzeller/PiPifier)
- App Store: [PiPifier](https://apps.apple.com/app/id1160374471)
- What it does: Picture in Picture for any HTML5 video
- License: MIT
- Languages: JavaScript + Swift
- Architecture: Safari extension
- Database: no, files

### Plug
- Repo: [wulkano/Plug](https://github.com/wulkano/Plug)
- App Store: [Plug](https://apps.apple.com/app/id1514182074)
- What it does: Hype Machine music player
- License: MIT
- Languages: Swift (Objective-C 9%)
- Database: no, files; Keychain

### QuickLook Video
- Repo: [Marginal/QLVideo](https://github.com/Marginal/QLVideo)
- App Store: [QuickLook Video](https://apps.apple.com/app/id6759566961)
- What it does: Finder thumbnails and previews for video files
- License: GPL-2.0
- Languages: Swift (C 3%)
- Architecture: Quick Look extension
- Database: no, files

### Reopen
- Repo: [Feng6611/mac-command-reopen](https://github.com/Feng6611/mac-command-reopen)
- App Store: [Reopen](https://apps.apple.com/app/id6757333924)
- What it does: makes Cmd+Tab restore minimised and closed windows
- License: MIT
- Languages: Swift
- Database: no, files

### Rocket.Chat
- Repo: [RocketChat/Rocket.Chat.Electron](https://github.com/RocketChat/Rocket.Chat.Electron)
- App Store: [Rocket.Chat](https://apps.apple.com/app/id1086818840)
- What it does: team chat client
- License: MIT
- Languages: TypeScript
- Architecture: Electron
- Database: no, browser localStorage and IndexedDB. Keychain through Electron's `safeStorage`, for Outlook credentials only

### Seahorse Studio
- Repo: [robaho/seashore](https://github.com/robaho/seashore)
- App Store: [Seahorse Studio](https://apps.apple.com/app/id6742335288)
- What it does: image editor
- License: GPL-2.0
- Languages: C + Objective-C
- Architecture: listed under a different name than the repo
- Database: no, files. The Keychain item is a purchase flag

### Stockfish Chess
- Repo: [daylen/stockfish-mac](https://github.com/daylen/stockfish-mac)
- App Store: [Stockfish Chess](https://apps.apple.com/app/id801463932)
- What it does: chess app
- License: GPL-3.0 (README)
- Languages: C++ + Objective-C
- Database: no, files

### stts
- Repo: [inket/stts](https://github.com/inket/stts)
- App Store: [stts](https://apps.apple.com/app/id1187772509)
- What it does: monitors the status of cloud services
- License: MIT
- Languages: Swift
- Database: no, files

### Table Tool
- Repo: [jakob/TableTool](https://github.com/jakob/TableTool)
- App Store: [Table Tool](https://apps.apple.com/app/id1122008420)
- What it does: CSV editor
- License: MIT
- Languages: Objective-C
- Database: no, files

### ThenGenerator
- Repo: [87kangsw/ThenGenerator](https://github.com/87kangsw/ThenGenerator)
- App Store: [ThenGenerator](https://apps.apple.com/app/id1499993324)
- What it does: Xcode source editor extension for Then
- License: MIT
- Languages: Swift
- Architecture: Xcode extension
- Database: no, preferences

### Thor
- Repo: [gbammc/Thor](https://github.com/gbammc/Thor)
- App Store: [Thor Launcher](https://apps.apple.com/app/id1120999687)
- What it does: switches apps with shortcuts
- License: MIT
- Languages: Swift
- Database: no, preferences

### UTM
- Repo: [utmapp/UTM](https://github.com/utmapp/UTM)
- App Store: [UTM Virtual Machines](https://apps.apple.com/app/id1538878817)
- What it does: virtual machines
- License: Apache-2.0 (uses some GPL and LGPL components)
- Languages: Objective-C + Swift
- Architecture: a second listing, UTM SE, is the retro PC emulator
- Database: no, files. The Keychain holds the UTM Remote TLS identity

### WiFi Lens Pro
- Repo: [ShiinaLabs/wifi-lens](https://github.com/ShiinaLabs/wifi-lens)
- App Store: [WiFi Lens Pro](https://apps.apple.com/app/id6776590746)
- What it does: Wi-Fi analyser and network diagnostics
- License: Apache-2.0
- Languages: Swift (Python 4%)
- Database: no, files

### WireGuard
- Repo: [WireGuard/wireguard-apple](https://github.com/WireGuard/wireguard-apple)
- App Store: [WireGuard](https://apps.apple.com/app/id1451685025)
- What it does: VPN client
- License: MIT
- Languages: C + Swift
- Architecture: the Go part (wireguard-go) is fetched at build time, so it is not counted above
- Database: no, preferences; Keychain
