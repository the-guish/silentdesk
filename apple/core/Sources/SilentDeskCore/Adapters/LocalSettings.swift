/// Settings, from the environment or given directly.

import Foundation

public struct LocalSettings: Settings {
    public static let defaultSlackRedirectPort = 47615

    public let dataDirectory: String
    public let now: String?
    /// A base URL per service, such as ["gmail": "http://127.0.0.1:8000"].
    let baseURLs: [String: String]
    public let googleClientID: String?
    public let googleClientSecret: String?
    public let slackClientID: String?
    public let slackRedirectPort: Int
    /// For tests only, see docs/specs/cli.md: a file that replaces the OS credential
    /// store, and a fake server that replaces every service.
    public let testKeyring: String?
    public let testBaseURL: String?
    /// Sign-in pages are fetched and their redirects followed, instead of
    /// opening a browser.
    public let testBrowser: Bool

    public init(
        dataDirectory: String,
        now: String? = nil,
        baseURLs: [String: String] = [:],
        googleClientID: String? = nil,
        googleClientSecret: String? = nil,
        slackClientID: String? = nil,
        slackRedirectPort: Int = LocalSettings.defaultSlackRedirectPort,
        testKeyring: String? = nil,
        testBaseURL: String? = nil,
        testBrowser: Bool = false
    ) {
        self.dataDirectory = dataDirectory
        self.now = now
        self.baseURLs = baseURLs
        self.googleClientID = googleClientID
        self.googleClientSecret = googleClientSecret
        self.slackClientID = slackClientID
        self.slackRedirectPort = slackRedirectPort
        self.testKeyring = testKeyring
        self.testBaseURL = testBaseURL.map { trimTrailingSlashes($0) }
        self.testBrowser = testBrowser
    }

    /// The data folder and the SILENTDESK_* variables in docs/specs/cli.md. Empty
    /// variables count as unset.
    public static func fromEnvironment(_ environment: [String: String] = ProcessInfo.processInfo.environment) -> LocalSettings {
        func variable(_ name: String) -> String? {
            guard let value = environment[name], !value.isEmpty else { return nil }
            return value
        }
        return LocalSettings(
            dataDirectory: dataDirectory(environment),
            now: variable("SILENTDESK_TEST_NOW"),
            googleClientID: variable("SILENTDESK_GOOGLE_CLIENT_ID"),
            googleClientSecret: variable("SILENTDESK_GOOGLE_CLIENT_SECRET"),
            slackClientID: variable("SILENTDESK_SLACK_CLIENT_ID"),
            slackRedirectPort: port(variable("SILENTDESK_SLACK_REDIRECT_PORT")),
            testKeyring: variable("SILENTDESK_TEST_KEYRING"),
            testBaseURL: variable("SILENTDESK_TEST_BASE_URL"),
            testBrowser: variable("SILENTDESK_TEST_BROWSER") == "follow"
        )
    }

    /// $XDG_DATA_HOME/silentdesk when set, as on Linux; otherwise the
    /// platform's place for an app's data (docs/specs/storage.md).
    static func dataDirectory(_ environment: [String: String]) -> String {
        if let xdg = environment["XDG_DATA_HOME"], !xdg.isEmpty {
            return trimTrailingSlashes(xdg) + "/silentdesk"
        }
        let home = environment["HOME"].flatMap { $0.isEmpty ? nil : $0 } ?? NSHomeDirectory()
        #if os(macOS)
        return home + "/Library/Application Support/SilentDesk"
        #else
        return home + "/.local/share/silentdesk"
        #endif
    }

    public func baseURL(_ service: String, default defaultURL: String) -> String {
        if let url = baseURLs[service] {
            return url
        }
        if let testBaseURL {
            return "\(testBaseURL)/\(service)"
        }
        return defaultURL
    }

    /// A port number; Slack's default when unset or not a valid port.
    static func port(_ text: String?) -> Int {
        guard let text, let value = Int(text), text.allSatisfy(\.isNumber), value > 0, value <= 0xFFFF else {
            return defaultSlackRedirectPort
        }
        return value
    }
}

private func trimTrailingSlashes(_ text: String) -> String {
    var text = text
    while text.hasSuffix("/") { text.removeLast() }
    return text
}
