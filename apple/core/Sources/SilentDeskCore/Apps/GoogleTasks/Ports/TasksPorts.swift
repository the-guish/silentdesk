/// What the Google Tasks app needs from outside. Only this app uses these.

/// Google sign-in: through the browser, then token refresh.
protocol TasksAuthorization: Sendable {
    /// Whether there is a client ID to sign in with.
    var configured: Bool { get }

    /// Opens Google's sign-in page and waits for the user. Throws an `auth`
    /// error unless every `required` scope is granted, with a refresh token.
    func signIn(scopes: [String], required: [String]) async throws -> GoogleTasksGrant

    /// A fresh access token. Throws an `auth` error when the grant is gone.
    func accessToken(refreshToken: String) async throws -> String

    /// Ends the grant at Google. Best effort.
    func revoke(refreshToken: String) async
}

/// Refresh tokens, one per service, kept in the OS credential store.
protocol TasksCredentials: Sendable {
    func refreshToken(_ service: String) throws -> String?
    func saveRefreshToken(_ service: String, _ token: String) throws
    func deleteRefreshToken(_ service: String) throws
}

/// The Google Tasks app's own tables in the shared database.
protocol TasksStateStore: Sendable {
    func load(_ service: String) async throws -> GoogleTasksState?
    func save(_ service: String, _ state: GoogleTasksState) async throws
    func clear(_ service: String) async throws
}

/// The Google Tasks REST API, read-only. Every call takes a current access token.
protocol TasksAPI: Sendable {
    /// The signed-in account's email address.
    func email(token: String) async throws -> String

    func lists(token: String) async throws -> [TaskList]

    /// Every task in the list Google returns: open ones, and any it still
    /// reports as completed or deleted.
    func tasks(token: String, in list: TaskList) async throws -> [GoogleTask]
}
