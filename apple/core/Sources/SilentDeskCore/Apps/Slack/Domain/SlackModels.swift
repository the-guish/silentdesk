/// Slack messages, as far as SilentDesk needs them. Message text is never
/// stored: only a preview of a conversation's newest message, as its title.

/// Without token rotation, a long-lived user token; with it, a 12-hour access
/// token and a refresh token.
struct SlackCredential: Sendable, Equatable {
    let accessToken: String
    let refreshToken: String?
    /// Unix seconds, or nil when the token does not expire.
    let expiresAt: Int?
}

struct SlackAccount: Sendable, Equatable {
    let userID: String
    let userName: String
    let teamID: String
    let teamName: String
}

/// One search result, as Slack returns it.
struct SlackMatch: Sendable, Equatable {
    let channelID: String
    /// For a 1:1 DM, the other user's ID.
    let channelName: String
    let isIM: Bool
    let isMPIM: Bool
    let user: String?
    let username: String?
    /// Slack's markup, with <@U1> mentions and <url|label> links.
    let text: String
    let ts: String
    let permalink: String
}

/// One message of a conversation, as conversations.history returns it.
struct SlackHistoryEntry: Sendable, Equatable {
    let user: String?
    let username: String?
    let text: String
    let ts: String
    /// Set for events, such as channel_join, rather than messages.
    let subtype: String?
}

struct SlackDirectMessage: Sendable, Equatable {
    let channelID: String
    let ts: String
    let direction: Direction
    let author: String
    /// The other person, or "Group DM".
    let counterpart: String
    /// The start of the message as plain text.
    let preview: String
    let permalink: String
    /// RFC 3339.
    let date: String
}
