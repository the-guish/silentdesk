/// The most recently updated open issues assigned to or reported by the user.
/// Connects with a token: an email and API token for Jira Cloud, or a
/// personal access token for Jira Data Center.
final class JiraConnector: Connector {
    private let api: any JiraAPI
    private let credentials: any JiraCredentials
    private let state: any JiraStateStore
    /// Where to reach a site, and Atlassian's gateway: their real addresses,
    /// or a test server.
    private let siteBase: @Sendable (String) -> String
    private let gatewayBase: @Sendable () -> String

    init(
        api: any JiraAPI,
        credentials: any JiraCredentials,
        state: any JiraStateStore,
        siteBase: @escaping @Sendable (String) -> String,
        gatewayBase: @escaping @Sendable () -> String
    ) {
        self.api = api
        self.credentials = credentials
        self.state = state
        self.siteBase = siteBase
        self.gatewayBase = gatewayBase
    }

    var service: String { JiraRules.service }

    func status() async throws -> ServiceStatus {
        let account = try await state.load()
        let connected = try account != nil && credentials.load() != nil
        // Jira needs no app registration: the user brings a token.
        return ServiceStatus(
            service: service, configured: true, connected: connected,
            account: connected ? account.map(JiraRules.accountLabel) : nil)
    }

    /// Checks the token against the site, then keeps it. `email` is set for
    /// Jira Cloud and empty for Data Center. Nothing is stored on failure.
    func connect(_ params: [String: String]) async throws -> ServiceStatus {
        let site = try JiraRules.normalizeSite(params["site"] ?? "")
        let token = (params["token"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else { throw ConnectorError.auth(service, "Enter an API token.") }
        let email = (params["email"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let credential = JiraCredential(email: email.isEmpty ? nil : email, token: token)
        let (endpoint, me) = try await findEndpoint(site, credential)
        try credentials.save(credential)
        try await state.save(JiraAccount(userID: me.id ?? "", userName: me.name, endpoint: endpoint))
        return try await status()
    }

    /// The site's own API first. Atlassian accepts a scoped Cloud token only
    /// through its gateway, so on 401 from a Cloud site the site's cloud ID
    /// is looked up and the gateway is tried.
    private func findEndpoint(_ site: String, _ credential: JiraCredential) async throws -> (JiraEndpoint, JiraUser) {
        let rejected = ConnectorError.auth(service, "Jira rejected the token. Check the site, email and API token.")
        let direct = JiraEndpoint(site: site, apiBase: siteBase(site), flavor: credential.flavor)
        do {
            return (direct, try await me(direct, credential))
        } catch let error as ConnectorError where error.kind == .auth {
            if credential.flavor != .cloud || !JiraRules.isCloudSite(site) {
                throw rejected
            }
        } catch let error as ConnectorError where error.kind == .remote {
            if error.status == 404 {
                throw ConnectorError.auth(service, "No Jira was found at \(site). Check the site address.")
            }
            throw error
        }
        guard let cloudID = try await api.cloudID(siteBase: siteBase(site)) else { throw rejected }
        let gateway = JiraEndpoint(site: site, apiBase: "\(gatewayBase())/\(cloudID)", flavor: credential.flavor)
        do {
            return (gateway, try await me(gateway, credential))
        } catch let error as ConnectorError where error.kind == .auth {
            throw rejected
        }
    }

    private func me(_ endpoint: JiraEndpoint, _ credential: JiraCredential) async throws -> JiraUser {
        let me = try await api.myself(endpoint, credential)
        guard me.id != nil else { throw ConnectorError.auth(service, "Jira did not identify the user.") }
        return me
    }

    /// Forgets the token and the account. Jira has no API to revoke an API
    /// token: the user revokes it in their Atlassian or Jira profile.
    func disconnect() async throws -> ServiceStatus {
        try credentials.delete()
        try await state.clear()
        return try await status()
    }

    func sync() async throws -> SyncResult {
        guard let account = try await state.load(), let credential = try credentials.load() else {
            throw ConnectorError.auth(service, "Jira is not connected.")
        }
        let issues: [JiraIssue]
        do {
            issues = try await api.openIssues(account.endpoint, credential, count: JiraRules.syncCount)
        } catch let error as ConnectorError where error.kind == .auth {
            // Expired or revoked: forget the token, keep the topics.
            try credentials.delete()
            throw ConnectorError.auth(service, "Jira rejected the token. Connect again.")
        }
        return SyncResult(
            topics: issues.prefix(JiraRules.syncCount).map { JiraRules.topic($0, account: account) }, removed: [],
            complete: true)
    }

    func reply(topicKey: String, body: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk cannot comment on a Jira issue yet.")
    }

    func history(topicKey: String) async throws -> [Message] {
        throw ConnectorError.unsupported(service, "Jira has no conversation to show.")
    }

    func deleteTopic(topicKey: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk cannot delete a Jira issue.")
    }

    func deleteItem(topicKey: String, itemKey: String) async throws -> Topic? {
        throw ConnectorError.unsupported(service, "SilentDesk cannot delete a Jira issue.")
    }
}
