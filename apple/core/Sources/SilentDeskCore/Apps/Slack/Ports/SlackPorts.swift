/// What the Slack app needs from outside. Only this app uses these.

/// Slack sign-in: OAuth v2 with PKCE through the browser, for a user token.
protocol SlackAuthorization: Sendable {
    /// Whether there is a Slack client ID to sign in with.
    var configured: Bool { get }

    /// Throws an `auth` error unless every user scope is granted.
    func signIn() async throws -> SlackCredential

    /// A new access token. Throws an `auth` error when the grant is gone.
    func refresh(_ credential: SlackCredential) async throws -> SlackCredential

    /// Ends the token at Slack. Best effort.
    func revoke(accessToken: String) async
}

/// The user token, kept in the OS credential store.
protocol SlackCredentials: Sendable {
    func load() throws -> SlackCredential?
    func save(_ credential: SlackCredential) throws
    func delete() throws
}

/// The Slack app's own table in the shared database.
protocol SlackStateStore: Sendable {
    func load() async throws -> SlackAccount?
    func save(_ account: SlackAccount) async throws
    func clear() async throws
}

/// The Slack Web API, read-only, with a user token.
protocol SlackAPI: Sendable {
    func identity(token: String) async throws -> SlackAccount

    /// Messages matching a search, newest first.
    func search(token: String, query: String, count: Int) async throws -> [SlackMatch]

    /// A conversation's `count` most recent messages. Needs the history scopes.
    func history(token: String, channelID: String, count: Int) async throws -> [SlackHistoryEntry]

    /// A user's display name, or empty when it cannot be read.
    func userName(token: String, userID: String) async throws -> String
}
