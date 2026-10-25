/// What the Gmail app needs from outside. Only this app uses these.

/// Google sign-in: through the browser, then token refresh.
protocol GmailAuthorization: Sendable {
    /// Whether there is a client ID to sign in with.
    var configured: Bool { get }

    /// Opens Google's sign-in page and waits for the user. Throws an `auth`
    /// error unless every `required` scope is granted, with a refresh token.
    func signIn(scopes: [String], required: [String]) async throws -> GmailGrant

    /// A fresh access token. Throws an `auth` error when the grant is gone.
    func accessToken(refreshToken: String) async throws -> String

    /// Ends the grant at Google. Best effort.
    func revoke(refreshToken: String) async
}

/// Gmail's refresh token, kept in the OS credential store.
protocol GmailCredentials: Sendable {
    func refreshToken() throws -> String?
    func saveRefreshToken(_ token: String) throws
    func deleteRefreshToken() throws
}

/// The Gmail app's own tables in the shared database: the account, and the
/// headers of every synced message.
protocol GmailStateStore: Sendable {
    func load() async throws -> GmailState?
    func save(_ state: GmailState) async throws
    /// Forgets the account and every message.
    func clear() async throws
    func knownIDs() async throws -> Set<String>
    func addMessages(_ messages: [GmailMessage]) async throws
    /// Messages by thread: of the given threads, or of every thread.
    func threads(_ threadIDs: [String]?) async throws -> [String: [GmailMessage]]
    func removeThread(_ threadID: String) async throws
    func removeMessage(_ messageID: String) async throws
}

/// Gmail's REST API, headers only. Every call takes a current access token.
protocol GmailAPI: Sendable {
    func profile(token: String) async throws -> GmailProfile

    /// Every message in the Inbox, newest first.
    func inboxIDs(token: String) async throws -> [String]

    /// Messages that entered the Inbox since `historyID`, and where the next
    /// sync starts; nil when Gmail no longer keeps history that old.
    func inboxChanges(token: String, since historyID: String) async throws -> (ids: [String], historyID: String)?

    /// The headers of each message, read at the pace Google allows, in the
    /// order of `ids`. Drafts, chats and messages deleted meanwhile are left
    /// out. `progress` gets how many were read so far.
    func messages(token: String, ids: [String], progress: @escaping @Sendable (Int) -> Void) async throws -> [GmailMessage]

    /// The headers a reply to the message needs.
    func original(token: String, messageID: String) async throws -> GmailOriginal

    /// Sends an RFC 5322 message in the thread.
    func send(token: String, threadID: String, message: String) async throws

    /// Moves the thread to the trash, where Gmail deletes it after 30 days.
    func trashThread(token: String, threadID: String) async throws

    /// Moves one message to the trash, where Gmail deletes it after 30 days.
    func trashMessage(token: String, messageID: String) async throws
}
