/// The Gmail Inbox: one topic per thread, its messages as items. Replies go
/// to the thread's newest message. Deleting moves the thread, or one message,
/// to the trash. Messages stay after they leave the Inbox.
final class GmailConnector: Connector {
    /// Messages read between two saves, so an interrupted first sync resumes
    /// where it stopped. Each batch also gets a fresh access token, which
    /// lasts an hour.
    static let saveEvery = 500

    private let api: any GmailAPI
    private let authorization: any GmailAuthorization
    private let credentials: any GmailCredentials
    private let state: any GmailStateStore

    init(api: any GmailAPI, authorization: any GmailAuthorization, credentials: any GmailCredentials, state: any GmailStateStore) {
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state
    }

    var service: String { GmailRules.service }

    func status() async throws -> ServiceStatus {
        guard try credentials.refreshToken() != nil else {
            return ServiceStatus(service: service, configured: authorization.configured, connected: false, account: nil)
        }
        let state = try await state.load()
        return ServiceStatus(service: service, configured: authorization.configured, connected: true, account: state?.email)
    }

    /// Signs in through the browser and keeps the refresh token. Another
    /// account's messages are forgotten; an older grant is revoked.
    func connect(_ params: [String: String]) async throws -> ServiceStatus {
        let grant = try await authorization.signIn(scopes: GmailRules.scopes, required: GmailRules.scopes)
        let email = try await api.profile(token: grant.accessToken).email
        if let old = try credentials.refreshToken(), old != grant.refreshToken {
            await authorization.revoke(refreshToken: old)
        }
        var state = try await state.load()
        if state == nil || state?.email != email {
            try await self.state.clear()
            state = GmailState(email: email, historyID: nil)
        }
        try credentials.saveRefreshToken(grant.refreshToken)
        try await self.state.save(state!)
        return try await status()
    }

    /// Revokes the grant at Google, then forgets it, the account and every message.
    func disconnect() async throws -> ServiceStatus {
        if let token = try credentials.refreshToken() {
            await authorization.revoke(refreshToken: token)
        }
        try credentials.deleteRefreshToken()
        try await state.clear()
        return try await status()
    }

    private func accessToken() async throws -> String {
        guard let refresh = try credentials.refreshToken() else {
            throw ConnectorError.auth(service, "Gmail is not connected.")
        }
        do {
            return try await authorization.accessToken(refreshToken: refresh)
        } catch let error as ConnectorError where error.kind == .auth {
            if authorization.configured {
                // The grant is gone: forget it, keep the messages and topics.
                try credentials.deleteRefreshToken()
            }
            throw ConnectorError.auth(service, "\(error.message) Connect Gmail again.")
        }
    }

    /// The first sync lists the whole Inbox; later ones list only what
    /// entered it since, until Gmail's history runs out (about a week).
    func sync() async throws -> SyncResult {
        var access = try await accessToken()
        // A sign-in kept from legacy has no account yet.
        let current: GmailState
        if let loaded = try await state.load() {
            current = loaded
        } else {
            current = GmailState(email: try await api.profile(token: access).email, historyID: nil)
        }
        var changes: (ids: [String], historyID: String)?
        if let since = current.historyID {
            changes = try await api.inboxChanges(token: access, since: since)
        }
        let ids: [String]
        let historyID: String
        if let changes {
            (ids, historyID) = changes
        } else {
            // Take the marker first, so changes made while listing come next time.
            historyID = try await api.profile(token: access).historyID
            ids = try await api.inboxIDs(token: access)
        }
        let fresh = GmailRules.newIDs(known: try await state.knownIDs(), ids)

        var touched = Set<String>()
        for offset in stride(from: 0, to: fresh.count, by: Self.saveEvery) {
            if offset > 0 {
                access = try await accessToken()
            }
            let batch = Array(fresh[offset..<min(offset + Self.saveEvery, fresh.count)])
            let messages = try await api.messages(token: access, ids: batch) { _ in }
            try await state.addMessages(messages)
            touched.formUnion(messages.map(\.threadID))
        }
        try await state.save(GmailState(email: current.email, historyID: historyID))

        // After a full listing, every stored thread: an interrupted sync may
        // have stored messages the desk has not seen.
        let threads = try await state.threads(changes == nil ? nil : touched.sorted())
        return SyncResult(
            topics: threads.map { GmailRules.topic(threadID: $0.key, messages: $0.value) }, removed: [], complete: false)
    }

    /// Sends `body`, typed by the user, as a reply to the thread's newest
    /// message. It joins the thread; no AI notice, as the user wrote it.
    func reply(topicKey: String, body: String) async throws {
        guard let thread = try await state.threads([topicKey])[topicKey], let newest = thread.max(by: {
            ($0.date, $0.messageID) < ($1.date, $1.messageID)
        }) else {
            throw UnknownTopic(message: "Gmail has no synced thread '\(topicKey)'.")
        }
        let access = try await accessToken()
        let original = try await api.original(token: access, messageID: newest.messageID)
        try await api.send(token: access, threadID: topicKey, message: GmailRules.reply(original, body: body))
    }

    func history(topicKey: String) async throws -> [Message] {
        throw ConnectorError.unsupported(service, "SilentDesk shows Gmail's headers only; it never reads a message's body.")
    }

    /// Moves the thread to the Gmail trash and forgets its messages.
    func deleteTopic(topicKey: String) async throws {
        let access = try await accessToken()
        try await api.trashThread(token: access, threadID: topicKey)
        try await state.removeThread(topicKey)
    }

    /// Moves one message to the Gmail trash and forgets it. The thread is
    /// titled anew from the messages left, or gone with its last one.
    func deleteItem(topicKey: String, itemKey: String) async throws -> Topic? {
        let access = try await accessToken()
        try await api.trashMessage(token: access, messageID: itemKey)
        try await state.removeMessage(itemKey)
        guard let messages = try await state.threads([topicKey])[topicKey], !messages.isEmpty else { return nil }
        return GmailRules.topic(threadID: topicKey, messages: messages)
    }
}
