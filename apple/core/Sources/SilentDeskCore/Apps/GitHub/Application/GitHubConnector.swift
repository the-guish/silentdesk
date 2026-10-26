/// Open pull requests that request the user's review, are assigned to the
/// user, or were opened by the user. Connects with a personal access token,
/// to github.com or a GitHub Enterprise Server.
final class GitHubConnector: Connector {
    private let api: any GitHubAPI
    private let credentials: any GitHubCredentials
    private let state: any GitHubStateStore
    /// Where to reach an endpoint's API: its own address, or a test server.
    private let apiBase: @Sendable (GitHubEndpoint) -> String

    init(
        api: any GitHubAPI,
        credentials: any GitHubCredentials,
        state: any GitHubStateStore,
        apiBase: @escaping @Sendable (GitHubEndpoint) -> String
    ) {
        self.api = api
        self.credentials = credentials
        self.state = state
        self.apiBase = apiBase
    }

    var service: String { GitHubRules.service }

    func status() async throws -> ServiceStatus {
        let account = try await state.load()
        let connected = try account != nil && credentials.token() != nil
        // GitHub needs no app registration: the user brings a token.
        return ServiceStatus(
            service: service, configured: true, connected: connected,
            account: connected ? account.map(GitHubRules.accountLabel) : nil)
    }

    /// Checks the token, then keeps it. `server` is empty for github.com, or
    /// a GitHub Enterprise Server host. Nothing is stored on failure.
    func connect(_ params: [String: String]) async throws -> ServiceStatus {
        let endpoint = try GitHubRules.endpoint(forServer: params["server"])
        let token = (params["token"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else { throw ConnectorError.auth(service, "Enter a personal access token.") }
        let me = try await api.me(apiBase: apiBase(endpoint), token: token)
        try credentials.saveToken(token)
        try await state.save(GitHubAccount(login: me.login, name: me.name ?? me.login, endpoint: endpoint))
        return try await status()
    }

    /// Forgets the token and the account. GitHub has no API to revoke a
    /// personal access token: the user deletes it in their GitHub settings.
    func disconnect() async throws -> ServiceStatus {
        try credentials.deleteToken()
        try await state.clear()
        return try await status()
    }

    func sync() async throws -> SyncResult {
        guard let account = try await state.load(), let token = try credentials.token() else {
            throw ConnectorError.auth(service, "GitHub is not connected.")
        }
        let found: GitHubFound
        do {
            found = try await api.openPullRequests(
                graphqlURL: GitHubRules.graphqlURL(apiBase(account.endpoint)), token: token, queries: GitHubRules.queries)
        } catch let error as ConnectorError where error.kind == .auth {
            // Expired or revoked: forget the token, keep the topics.
            try credentials.deleteToken()
            throw ConnectorError.auth(service, "GitHub rejected the token. Connect again.")
        }
        // A partial answer updates what it found and keeps the other topics.
        return SyncResult(
            topics: GitHubRules.merge(found.pulls).map(GitHubRules.topic), removed: [], complete: found.complete)
    }

    func reply(topicKey: String, body: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk cannot reply to a pull request.")
    }

    func history(topicKey: String) async throws -> [Message] {
        throw ConnectorError.unsupported(service, "GitHub has no conversation to show.")
    }

    func deleteTopic(topicKey: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk cannot delete a pull request.")
    }

    func deleteItem(topicKey: String, itemKey: String) async throws -> Topic? {
        throw ConnectorError.unsupported(service, "SilentDesk cannot delete a pull request.")
    }
}
