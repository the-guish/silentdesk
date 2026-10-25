/// The Gmail app's tables: gmail_state and gmail_messages (spec/sql/).
final class GmailSqlcipherStateStore: GmailStateStore {
    private static let columns = "message_id, thread_id, direction, sender, subject, date"

    private let database: any Database

    init(database: any Database) {
        self.database = database
    }

    func load() async throws -> GmailState? {
        try database.transaction { db in
            try db.queryOne("SELECT email, history_id FROM gmail_state WHERE id = 1").map {
                GmailState(email: $0[0].string ?? "", historyID: $0[1].string)
            }
        }
    }

    func save(_ state: GmailState) async throws {
        try database.transaction { db in
            try db.execute(
                "INSERT INTO gmail_state (id, email, history_id) VALUES (1, ?, ?)"
                    + " ON CONFLICT (id) DO UPDATE SET email = excluded.email, history_id = excluded.history_id",
                [.text(state.email), .text(state.historyID)])
        }
    }

    func clear() async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM gmail_state")
            try db.execute("DELETE FROM gmail_messages")
        }
    }

    func knownIDs() async throws -> Set<String> {
        try database.transaction { db in
            Set(try db.query("SELECT message_id FROM gmail_messages").compactMap { $0[0].string })
        }
    }

    func addMessages(_ messages: [GmailMessage]) async throws {
        try database.transaction { db in
            for message in messages {
                try db.execute(
                    "INSERT OR IGNORE INTO gmail_messages (\(Self.columns)) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        .text(message.messageID), .text(message.threadID), .text(message.direction.rawValue),
                        .text(message.sender), .text(message.subject), .text(message.date),
                    ])
            }
        }
    }

    func threads(_ threadIDs: [String]?) async throws -> [String: [GmailMessage]] {
        try database.transaction { db in
            let rows: [[SQLValue]]
            if let threadIDs {
                guard !threadIDs.isEmpty else { return [:] }
                let marks = Array(repeating: "?", count: threadIDs.count).joined(separator: ",")
                rows = try db.query(
                    "SELECT \(Self.columns) FROM gmail_messages WHERE thread_id IN (\(marks))", threadIDs.map { .text($0) })
            } else {
                rows = try db.query("SELECT \(Self.columns) FROM gmail_messages")
            }
            var threads: [String: [GmailMessage]] = [:]
            for row in rows {
                let message = GmailMessage(
                    messageID: row[0].string ?? "",
                    threadID: row[1].string ?? "",
                    direction: Direction(rawValue: row[2].string ?? "") ?? .inbound,
                    sender: row[3].string ?? "",
                    subject: row[4].string ?? "",
                    date: row[5].string ?? "")
                threads[message.threadID, default: []].append(message)
            }
            return threads
        }
    }

    func removeThread(_ threadID: String) async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM gmail_messages WHERE thread_id = ?", [.text(threadID)])
        }
    }

    func removeMessage(_ messageID: String) async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM gmail_messages WHERE message_id = ?", [.text(messageID)])
        }
    }
}
