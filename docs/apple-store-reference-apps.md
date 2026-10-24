# Apple Store Reference Apps

Status: reference · Last updated: 2026-10-24

Open-source apps confirmed on the Mac App Store, as a reference for publishing SilentDesk there.

**How they were found.**
- 48 come from the [open-source-mac-os-apps](https://github.com/serhii-londar/open-source-mac-os-apps) list, keeping those whose README links a Mac App Store listing.
- The other 7 were checked one by one: UTM, Krita, Telegram, WireGuard, Gifski, Hidden Bar and LibreOffice.
- Every listing was confirmed with Apple's iTunes lookup or search API.

**Languages** are bytes per language in the repository, the way GitHub counts them. A combination lists every language with at least 10% of the code, and smaller shares are in brackets. Vendored code, submodules and build scripts (Shell, Ruby, Perl) are not counted. Code fetched at build time is not counted either.

**Database** comes from searching the code and the dependency manifests for storage APIs and libraries. "Files" means preferences (`UserDefaults`) and files the app writes itself.

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
| No database: preferences and files | 38 (69%) |
| SQLite, directly | 5 (9%) |
| Core Data or SwiftData, which store in SQLite | 4 (7%) |
| Electron or Tauri storage | 4 (7%) |
| CloudKit sync, no local database | 2 (4%) |
| Embedded Firebird | 1 (2%) |
| Nothing stored | 1 (2%) |

- **Python:** under 10% in every app. Krita is the only one where we know it ships, as its plugin runtime.
- **Keychain:** 13 apps use it for secrets.

## Apps

| App | Repo | What it does | Languages | Architecture | Database |
|---|---|---|---|---|---|
| [ArtWall](https://apps.apple.com/app/id1178151992) | [JustinFincher/ASWP-for-macOS](https://github.com/JustinFincher/ASWP-for-macOS) | ArtStation artwork as wallpaper | Objective-C | Listed under a different name than the repo | No, files |
| [AutoMute](https://apps.apple.com/app/id1118136179) | [yonilevy/automute](https://github.com/yonilevy/automute) | Mutes sound when headphones disconnect or the Mac wakes | C++ + Objective-C | | No, files |
| [BarTranslate](https://apps.apple.com/app/id6759278154) | [ThijmenDam/BarTranslate](https://github.com/ThijmenDam/BarTranslate) | Menu bar translator | Swift | | No, files |
| [Better Resource Monitor](https://apps.apple.com/app/id6758237306) | [alexx855/better-resource-monitor](https://github.com/alexx855/better-resource-monitor) | Menu bar CPU, memory, disk, GPU and network monitor | JavaScript + Rust + TypeScript | Tauri v2, sandboxed. Also a DMG on GitHub Releases, without automatic updates | Tauri store plugin (a JSON file) |
| [Boop](https://apps.apple.com/app/id1518425043) | [IvanMathy/Boop](https://github.com/IvanMathy/Boop) | Scriptable scratchpad for developers | JavaScript + Swift | | No, files |
| [Chord Detector](https://apps.apple.com/app/id1219549675) | [cemolcay/ChordDetector](https://github.com/cemolcay/ChordDetector) | Menu bar app that detects the chords of the playing song | Swift | | No, files |
| [Cleaner for Xcode](https://apps.apple.com/app/id1296084683) | [waylybaye/XcodeCleaner](https://github.com/waylybaye/XcodeCleaner) | Frees disk space used by Xcode | JavaScript + Objective-C | React Native for macOS | No, files |
| [Clipbara](https://apps.apple.com/app/id6803537696) | [mobrava/Clipbara](https://github.com/mobrava/Clipbara) | Clipboard manager with pinboards | Swift | One listing shared with iPhone and iPad | SwiftData (SQLite), CloudKit sync |
| [Core-Monitor](https://apps.apple.com/app/id6762558526) | [offyotto/Core-Monitor](https://github.com/offyotto/Core-Monitor) | System monitor with menu bar stats and fan control | Swift (Python 2%) | | No, files |
| [CotEditor](https://apps.apple.com/app/id1024640650) | [coteditor/CotEditor](https://github.com/coteditor/CotEditor) | Plain-text editor | Swift | | No, files |
| [DiskWise](https://apps.apple.com/app/id6813265402) | [DreamOfXM/diskwise](https://github.com/DreamOfXM/diskwise) | Disk cleaner that moves files to the Trash | Swift + TypeScript | | No, files |
| [Equinox](https://apps.apple.com/app/id1591510203) | [rlxone/Equinox](https://github.com/rlxone/Equinox) | Creates dynamic wallpapers | Swift | | No, files |
| [Flycut](https://apps.apple.com/app/id442160987) | [TermiT/flycut](https://github.com/TermiT/flycut) | Clipboard manager for developers | Objective-C (Swift 6%, C 3%) | | No, preferences; CloudKit sync |
| [FolderForge](https://apps.apple.com/app/id6799417746) | [KeplSiv/FolderForge](https://github.com/KeplSiv/FolderForge) | Customises folder colours and icons | Swift (Python 2%) | | No, files |
| [FSNotes](https://apps.apple.com/app/id1277179284) | [glushchenko/fsnotes](https://github.com/glushchenko/fsnotes) | Notes manager in the style of nvALT | JavaScript + Swift | Notes are plain Markdown files | No, Markdown files; Keychain |
| [Gifski](https://apps.apple.com/app/id1351639930) | [sindresorhus/Gifski](https://github.com/sindresorhus/Gifski) | Converts videos to GIFs | Rust + Swift | Swift app with the Rust gifski encoder in the repo. Also a separate build for people without App Store access | No, files |
| [Hidden Bar](https://apps.apple.com/app/id1452453066) | [dwarvesf/hidden](https://github.com/dwarvesf/hidden) | Hides menu bar icons | Swift (Objective-C 4%) | Also notarised for download outside the store | No, files |
| [InjectionIII](https://apps.apple.com/app/id1380446739) | [johnno1962/InjectionIII](https://github.com/johnno1962/InjectionIII) | Live code injection for Swift development | C + Objective-C + Swift (Java 7%) | Listed under a different seller than the repo owner | No, files |
| [ItsPaint](https://apps.apple.com/app/id6796493980) | [joshlin2201/itspaint](https://github.com/joshlin2201/itspaint) | Paint and screenshot markup | Swift | | No, files |
| [JustMD](https://apps.apple.com/app/id6779422717) | [yuraist/just-md](https://github.com/yuraist/just-md) | Markdown editor with PDF export | Swift (Python 5%, TypeScript 3%) | | No, files |
| [Kiwix](https://apps.apple.com/app/id997079563) | [kiwix/apple](https://github.com/kiwix/apple) | Offline Wikipedia and other content | Swift (Objective-C 6%, JavaScript 3%) | Reads ZIM content files. One listing shared with iPhone and iPad | Core Data (SQLite) |
| [Krita](https://apps.apple.com/app/id1594607976) | [KDE/krita](https://github.com/KDE/krita) | Digital painting | C++ (Python 3%) | C++/Qt app that runs Python 3.10 inside it for plugins. The team reports months of work on the sandbox, and the sandbox stops plugins from running `xcrun` | SQLite through Qt SQL (resource cache) |
| [KubeContext](https://apps.apple.com/app/id1438838068) | [turkenh/KubeContext](https://github.com/turkenh/KubeContext) | Switches Kubernetes contexts | Swift | | No, files |
| [LibreOffice](https://apps.apple.com/app/id1630474372) | [LibreOffice/core](https://github.com/LibreOffice/core) | Office suite | C++ (Java 6%) | Published by The Document Foundation for a fee. The store build leaves Java out | Embedded Firebird for Base (HSQLDB needs Java) |
| [Localizable.strings](https://apps.apple.com/app/id1063953896) | [cristibaluta/Localizable.strings](https://github.com/cristibaluta/Localizable.strings) | Localises iOS and macOS projects | Swift | | No, files |
| [LosslessCut](https://apps.apple.com/app/id1505323402) | [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | Lossless video and audio editing | TypeScript | Electron | electron-store (a JSON file) |
| [MacPacker](https://apps.apple.com/app/id6473273874) | [sarensw/MacPacker](https://github.com/sarensw/MacPacker) | Archive manager | Swift (C++ 6%) | | No, files |
| [Medis 2](https://apps.apple.com/app/id1579200037) | [luin/medis](https://github.com/luin/medis) | Redis GUI | JavaScript (TypeScript 7%) | Electron | Browser localStorage |
| [MeetingBar](https://apps.apple.com/app/id1532419400) | [leits/MeetingBar](https://github.com/leits/MeetingBar) | Menu bar app for calendar meetings | Swift | | No, files; Keychain |
| [Menu Bar Percent Calculator](https://apps.apple.com/app/id1286560999) | [cemolcay/PercentCalculator](https://github.com/cemolcay/PercentCalculator) | Calculates percentages | Swift | | Stores nothing |
| [Nightwatch](https://apps.apple.com/app/id6816390602) | [rsutcliffe/nightwatch](https://github.com/rsutcliffe/nightwatch) | Clear-sky alerts for amateur astronomers | C + Swift | | No, files; Keychain |
| [Notenik](https://apps.apple.com/app/id1465997984) | [hbowie/notenik-swift](https://github.com/hbowie/notenik-swift) | Note-taking | Swift | | No, files |
| [OpenHabitTracker](https://apps.apple.com/app/id6654885470) | [Jinjinov/OpenHabitTracker](https://github.com/Jinjinov/OpenHabitTracker) | Notes, tasks and habit tracking | C# | .NET app. One listing shared with iPhone and iPad | SQLite through Entity Framework Core |
| [PageExtender](https://apps.apple.com/app/id1457557274) | [fphilipe/PageExtender.app](https://github.com/fphilipe/PageExtender.app) | Safari extension that adds your own CSS and JS to pages | Swift (JavaScript 7%) | Safari extension | No, files |
| [Pesty](https://apps.apple.com/app/id6784511397) | [momenbasel/pesty](https://github.com/momenbasel/pesty) | Clipboard manager inspired by Paste | Swift | One listing shared with iPhone and iPad | No, files; CloudKit sync |
| [Pi Stats](https://apps.apple.com/app/id1514075262) | [Bunn/PiStats](https://github.com/Bunn/PiStats) | Shows Pi-hole statistics | Swift | | No, files; Keychain |
| [PiPifier](https://apps.apple.com/app/id1160374471) | [arnoappenzeller/PiPifier](https://github.com/arnoappenzeller/PiPifier) | Picture in Picture for any HTML5 video | JavaScript + Swift | Safari extension | No, files |
| [Plug](https://apps.apple.com/app/id1514182074) | [wulkano/Plug](https://github.com/wulkano/Plug) | Hype Machine music player | Swift (Objective-C 9%) | | No, files; Keychain |
| [Podlive](https://apps.apple.com/app/id1210411572) | [Podlive/podlive-macos](https://github.com/Podlive/podlive-macos) | Live-streaming podcast player | Objective-C | | Core Data (SQLite), plus calls to SQLite's C API; Keychain |
| [QuickLook Video](https://apps.apple.com/app/id6759566961) | [Marginal/QLVideo](https://github.com/Marginal/QLVideo) | Finder thumbnails and previews for video files | Swift (C 3%) | Quick Look extension | No, files |
| [Reopen](https://apps.apple.com/app/id6757333924) | [Feng6611/mac-command-reopen](https://github.com/Feng6611/mac-command-reopen) | Makes Cmd+Tab restore minimised and closed windows | Swift | | No, files |
| [Rocket.Chat](https://apps.apple.com/app/id1086818840) | [RocketChat/Rocket.Chat.Electron](https://github.com/RocketChat/Rocket.Chat.Electron) | Team chat client | TypeScript | Electron | Browser localStorage and IndexedDB; Keychain |
| [Seahorse Studio](https://apps.apple.com/app/id6742335288) | [robaho/seashore](https://github.com/robaho/seashore) | Image editor | C + Objective-C | Listed under a different name than the repo | No, files; Keychain |
| [Sequel Ace](https://apps.apple.com/app/id1518036000) | [Sequel-Ace/Sequel-Ace](https://github.com/Sequel-Ace/Sequel-Ace) | MySQL and MariaDB client | Objective-C + Swift | | SQLite through FMDB, for query history; Keychain |
| [Starcat](https://apps.apple.com/app/id6788809803) | [starcat-app/Starcat](https://github.com/starcat-app/Starcat) | Local-first manager for GitHub stars | JavaScript + Swift | | SQLite through GRDB (the code mentions SQLCipher); Keychain |
| [Stockfish Chess](https://apps.apple.com/app/id801463932) | [daylen/stockfish-mac](https://github.com/daylen/stockfish-mac) | Chess app | C++ + Objective-C | | No, files |
| [stts](https://apps.apple.com/app/id1187772509) | [inket/stts](https://github.com/inket/stts) | Monitors the status of cloud services | Swift | | No, files |
| [Table Tool](https://apps.apple.com/app/id1122008420) | [jakob/TableTool](https://github.com/jakob/TableTool) | CSV editor | Objective-C | | No, files |
| [Telegram](https://apps.apple.com/app/id747648890) | [TelegramMessenger/Telegram-macOS](https://github.com/TelegramMessenger/Telegram-macOS) | Messaging | C + Swift (JavaScript 3%, C++ 3%) | Its Postbox storage layer runs on SQLite. The source link on macos.telegram.org (overtake/TelegramSwift) is no longer public | SQLite encrypted with SQLCipher; Keychain |
| [ThenGenerator](https://apps.apple.com/app/id1499993324) | [87kangsw/ThenGenerator](https://github.com/87kangsw/ThenGenerator) | Xcode source editor extension for Then | Swift | Xcode extension | No, preferences |
| [Thor](https://apps.apple.com/app/id1120999687) | [gbammc/Thor](https://github.com/gbammc/Thor) | Switches apps with shortcuts | Swift | | No, preferences |
| [tmpNote](https://apps.apple.com/app/id1293664761) | [buddax2/tmpNote](https://github.com/buddax2/tmpNote) | Temporary notes | Swift | | Core Data (SQLite), CloudKit sync |
| [UTM](https://apps.apple.com/app/id1538878817) | [utmapp/UTM](https://github.com/utmapp/UTM) | Virtual machines | Objective-C + Swift | A second listing, UTM SE, is the retro PC emulator | No, files; Keychain |
| [WiFi Lens Pro](https://apps.apple.com/app/id6776590746) | [ShiinaLabs/wifi-lens](https://github.com/ShiinaLabs/wifi-lens) | Wi-Fi analyser and network diagnostics | Swift (Python 4%) | | No, files |
| [WireGuard](https://apps.apple.com/app/id1451685025) | [WireGuard/wireguard-apple](https://github.com/WireGuard/wireguard-apple) | VPN client | C + Swift | The Go part (wireguard-go) is fetched at build time, so it is not counted above | No, preferences; Keychain |
