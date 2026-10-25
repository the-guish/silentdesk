/// Gmail messages, as far as SilentDesk needs them: headers and labels only.
/// Bodies and attachments are never fetched.

struct GmailGrant: Sendable {
    let accessToken: String
    let refreshToken: String
}

struct GmailMessage: Sendable, Equatable {
    let messageID: String
    let threadID: String
    /// Outbound when Gmail labels it SENT.
    let direction: Direction
    /// The From header, as written.
    let sender: String
    let subject: String
    /// RFC 3339, from Gmail's internal date.
    let date: String
}

/// The headers of the message a reply answers.
struct GmailOriginal: Sendable, Equatable {
    let direction: Direction
    let sender: String
    let to: String
    let replyTo: String
    let subject: String
    /// The RFC 5322 Message-ID, not Gmail's ID.
    let headerID: String
    let references: String
}

/// What the Gmail app remembers between syncs.
struct GmailState: Sendable, Equatable {
    /// The connected account.
    let email: String
    /// Where the next sync starts. Nil before the first full sync.
    let historyID: String?
}

/// A sync's profile: the account, and a marker for the mailbox's current state.
struct GmailProfile: Sendable, Equatable {
    let email: String
    /// Changes after it can be listed.
    let historyID: String
}
