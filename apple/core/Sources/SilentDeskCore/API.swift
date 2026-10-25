/// The core's public API: one function per command in spec/cli.md.
///
/// The CLI and the apps use only this. Everything it returns is plain data,
/// shaped as the contract describes. It is also where the apps are wired
/// together: each app's adapters, then the desk on top of every connector.

import Foundation

public enum API {
    /// The version of spec/cli.md this core implements.
    public static let contract = 1
    /// This core's own version.
    public static let coreVersion = "0.1.0"

    public static func version() -> Version {
        Version(contract: contract, implementation: "swift", version: coreVersion)
    }

    /// The desk with every connector app wired in, with settings from the
    /// environment unless given. Building it does no I/O.
    public static func desk(settings: LocalSettings = .fromEnvironment()) -> any Desk {
        let keyring: any Keyring = settings.testKeyring.map { FileKeyring(path: $0) } ?? SystemKeyring()
        let database = SqlcipherDatabase(path: settings.dataDirectory + "/silentdesk.db", keyring: keyring)
        let http = URLSessionHttp(allowLoopbackHTTP: settings.testBaseURL != nil)
        let browser: any Browser = settings.testBrowser ? FollowingBrowser(http: http) : SystemBrowser()
        let oauth = LoopbackOAuth(http: http, browser: browser)
        let connectors: [any Connector] = [
            GmailWiring.create(settings: settings, database: database, keyring: keyring, http: http, oauth: oauth),
            GitHubWiring.create(settings: settings, database: database, keyring: keyring, http: http),
            GoogleTasksWiring.create(settings: settings, database: database, keyring: keyring, http: http, oauth: oauth),
            JiraWiring.create(settings: settings, database: database, keyring: keyring, http: http),
            SlackWiring.create(settings: settings, database: database, keyring: keyring, http: http, oauth: oauth),
        ]
        return DeskWiring.create(connectors: connectors, settings: settings, database: database)
    }
}

public struct Version: Codable, Equatable, Sendable {
    public let contract: Int
    public let implementation: String
    public let version: String
}
