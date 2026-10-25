/// Google Tasks, as far as SilentDesk needs them. Notes are never kept.

struct GoogleTasksGrant: Sendable {
    let accessToken: String
    let refreshToken: String
}

struct TaskList: Sendable, Equatable {
    let listID: String
    let title: String
}

struct GoogleTask: Sendable, Equatable {
    let taskID: String
    let listID: String
    let listTitle: String
    let title: String
    let completed: Bool
    let deleted: Bool
    /// YYYY-MM-DD: Google keeps the day only.
    let due: String?
    /// Where the task came from: "Gmail", "Docs" or "Chat".
    let origin: String?
    let url: String
    /// RFC 3339.
    let updated: String
}

/// What the Google Tasks app remembers between syncs.
struct GoogleTasksState: Sendable, Equatable {
    /// The connected account.
    let email: String
}

extension GoogleTasksGrant: CustomStringConvertible {
    var description: String { "GoogleTasksGrant(tokens hidden)" }
}
