/// What the GitHub app needs from outside. Only this app uses these.

struct GitHubMe: Sendable, Equatable {
    let login: String
    /// Nil when the user has not set a display name.
    let name: String?
}

/// GitHub's REST and GraphQL APIs, read-only, with a personal access token.
protocol GitHubAPI: Sendable {
    /// The token's user. Throws an `auth` error when GitHub rejects the token.
    func me(apiBase: String, token: String) async throws -> GitHubMe

    /// The pull requests each search query finds, with its reason, in one
    /// GraphQL request to `graphqlURL`.
    func openPullRequests(
        graphqlURL: String, token: String, queries: [(query: String, reason: GitHubReason)]
    ) async throws -> [PullRequest]
}

/// The personal access token, kept in the OS credential store.
protocol GitHubCredentials: Sendable {
    func token() throws -> String?
    func saveToken(_ token: String) throws
    func deleteToken() throws
}

/// The GitHub app's own table in the shared database.
protocol GitHubStateStore: Sendable {
    func load() async throws -> GitHubAccount?
    func save(_ account: GitHubAccount) async throws
    func clear() async throws
}
