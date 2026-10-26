/// What the Jira app needs from outside. Only this app uses these.

/// Jira's REST API, read-only.
protocol JiraAPI: Sendable {
    /// The credential's user. Throws an `auth` error when Jira rejects it.
    func myself(_ endpoint: JiraEndpoint, _ credential: JiraCredential) async throws -> JiraUser

    /// A Jira Cloud site's cloud ID, for Atlassian's gateway; nil when the
    /// site does not say.
    func cloudID(siteBase: String) async throws -> String?

    /// The `count` most recently updated open issues assigned to or reported
    /// by the user.
    func openIssues(_ endpoint: JiraEndpoint, _ credential: JiraCredential, count: Int) async throws -> [JiraIssue]
}

/// The email and token, kept in the OS credential store.
protocol JiraCredentials: Sendable {
    func load() throws -> JiraCredential?
    func save(_ credential: JiraCredential) throws
    func delete() throws
}

/// The Jira app's own table in the shared database.
protocol JiraStateStore: Sendable {
    func load() async throws -> JiraAccount?
    func save(_ account: JiraAccount) async throws
    func clear() async throws
}
