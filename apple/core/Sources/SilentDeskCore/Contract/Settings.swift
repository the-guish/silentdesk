/// Settings for one run of the core.
protocol Settings: Sendable {
    /// Where the database lives, such as ~/.local/share/silentdesk.
    var dataDirectory: String { get }

    /// A fixed time in RFC 3339, for repeatable tests. Nil uses the system clock.
    var now: String? { get }

    /// The service's API address: `default`, unless tests point the core at a fake server.
    func baseURL(_ service: String, default: String) -> String

    var googleClientID: String? { get }
    var googleClientSecret: String? { get }
    var slackClientID: String? { get }

    /// Slack matches redirect URLs exactly, so the sign-in port is fixed.
    var slackRedirectPort: Int { get }
}
