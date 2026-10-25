/// Every open task in Google Tasks, read-only: one topic per task, with one
/// item. Signs in with the Google client Gmail uses, but with its own
/// read-only grant and refresh token.
final class GoogleTasksConnector: Connector {
    private let api: any TasksAPI
    private let authorization: any TasksAuthorization
    private let credentials: any TasksCredentials
    private let state: any TasksStateStore

    init(api: any TasksAPI, authorization: any TasksAuthorization, credentials: any TasksCredentials, state: any TasksStateStore) {
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state
    }

    var service: String { TasksRules.service }

    func status() async throws -> ServiceStatus {
        guard try credentials.refreshToken(service) != nil else {
            return ServiceStatus(service: service, configured: authorization.configured, connected: false, account: nil)
        }
        let state = try await state.load(service)
        return ServiceStatus(service: service, configured: authorization.configured, connected: true, account: state?.email)
    }

    /// Signs in through the browser for read-only access, then keeps the
    /// refresh token. A previous grant for another sign-in is revoked.
    func connect(_ params: [String: String]) async throws -> ServiceStatus {
        let grant = try await authorization.signIn(scopes: TasksRules.scopes, required: TasksRules.requiredScopes)
        let email = try await api.email(token: grant.accessToken)
        if let old = try credentials.refreshToken(service), old != grant.refreshToken {
            await authorization.revoke(refreshToken: old)
        }
        try credentials.saveRefreshToken(service, grant.refreshToken)
        try await state.save(service, GoogleTasksState(email: email))
        return try await status()
    }

    /// Revokes the grant at Google, then forgets the token and the account.
    func disconnect() async throws -> ServiceStatus {
        if let token = try credentials.refreshToken(service) {
            await authorization.revoke(refreshToken: token)
        }
        try credentials.deleteRefreshToken(service)
        try await state.clear(service)
        return try await status()
    }

    func sync() async throws -> SyncResult {
        guard let refresh = try credentials.refreshToken(service) else {
            throw ConnectorError.auth(service, "Google Tasks is not connected.")
        }
        let access: String
        do {
            access = try await authorization.accessToken(refreshToken: refresh)
        } catch let error as ConnectorError where error.kind == .auth {
            if authorization.configured {
                // The grant is gone: forget it, keep the topics.
                try credentials.deleteRefreshToken(service)
            }
            throw ConnectorError.auth(service, "\(error.message) Connect Google Tasks again.")
        }
        var found: [GoogleTask] = []
        for list in try await api.lists(token: access) {
            found += try await api.tasks(token: access, in: list)
        }
        return SyncResult(topics: found.filter(TasksRules.isOpen).map(TasksRules.topic), removed: [], complete: true)
    }

    func reply(topicKey: String, body: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk cannot reply to a task.")
    }

    func history(topicKey: String) async throws -> [Message] {
        throw ConnectorError.unsupported(service, "Google Tasks has no conversation to show.")
    }

    func deleteTopic(topicKey: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk has read-only access to Google Tasks.")
    }

    func deleteItem(topicKey: String, itemKey: String) async throws -> Topic? {
        throw ConnectorError.unsupported(service, "SilentDesk has read-only access to Google Tasks.")
    }
}
