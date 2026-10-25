/// The user's default browser, and a stand-in for tests.

import Foundation

struct BrowserError: Error, CustomStringConvertible {
    let message: String
    var description: String { message }
}

final class SystemBrowser: Browser {
    func open(_ url: String) async throws {
        guard URL(string: url)?.scheme == "https" else {
            throw BrowserError(message: "Only https pages are opened: \(url)")
        }
        #if os(macOS) || os(Linux)
        let process = Process()
        #if os(macOS)
        process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        #else
        process.executableURL = URL(fileURLWithPath: "/usr/bin/xdg-open")
        #endif
        process.arguments = [url]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw BrowserError(message: "No web browser could be opened.")
        }
        #else
        // The app signs in with its own browser session; this core opens none.
        throw BrowserError(message: "No web browser can be opened from the core on this platform.")
        #endif
    }
}

/// For tests only (SILENTDESK_TEST_BROWSER=follow): fetches the page and
/// follows its redirects, as a browser would after the user signs in.
final class FollowingBrowser: Browser {
    private let http: any Http

    init(http: any Http) {
        self.http = http
    }

    func open(_ url: String) async throws {
        _ = try await http.request("GET", url)
    }
}
