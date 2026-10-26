/// The desk's tables: desk_topics, desk_items and desk_values (spec/sql/).
/// Projects are not in this core yet; a topic keeps the one it has.
final class SqlcipherTopicStore: TopicStore {
    static let lastSyncedName = "last_synced"

    private let database: any Database

    init(database: any Database) {
        self.database = database
    }

    func topics() async throws -> [TopicRecord] {
        try database.transaction { db in
            let topics = try db.query("SELECT id, service, key, title, created_at, updated_at, deletable, project_id, status_name,"
                    + " status_category FROM desk_topics")
            let rows = try db.query(
                "SELECT topic_id, key, direction, author, url, date, deletable FROM desk_items ORDER BY topic_id, position")
            var items: [String: [Item]] = [:]
            for row in rows {
                let item = Item(
                    key: row[1].string ?? "",
                    direction: row[2].string.flatMap(Direction.init(rawValue:)),
                    author: row[3].string,
                    url: row[4].string,
                    date: row[5].string ?? "",
                    deletable: row[6].bool)
                items[row[0].string ?? "", default: []].append(item)
            }
            return topics.map { row in
                let id = row[0].string ?? ""
                return TopicRecord(
                    id: id,
                    service: row[1].string ?? "",
                    key: row[2].string ?? "",
                    title: row[3].string ?? "",
                    items: items[id] ?? [],
                    createdAt: row[4].string ?? "",
                    updatedAt: row[5].string ?? "",
                    deletable: row[6].bool,
                    projectId: row[7].string,
                    status: row[8].string.map {
                        TopicStatus(name: $0, category: row[9].string.flatMap(StatusCategory.init(rawValue:)))
                    })
            }
        }
    }

    func replace(_ service: String, with records: [TopicRecord]) async throws {
        try database.transaction { db in
            // Their items go with them (ON DELETE CASCADE).
            try db.execute("DELETE FROM desk_topics WHERE service = ?", [.text(service)])
            for record in records {
                try db.execute(
                    // A project deleted while the service synced leaves its
                    // topics in Default.
                    "INSERT INTO desk_topics (id, service, key, title, created_at, updated_at, deletable, project_id,"
                        + " status_name, status_category)"
                        + " VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT id FROM desk_projects WHERE id = ?), ?, ?)",
                    [
                        .text(record.id), .text(service), .text(record.key), .text(record.title),
                        .text(record.createdAt), .text(record.updatedAt), .bool(record.deletable),
                        .text(record.projectId), .text(record.status?.name), .text(record.status?.category?.rawValue),
                    ])
                for (position, item) in record.items.enumerated() {
                    try db.execute(
                        "INSERT INTO desk_items (topic_id, position, key, direction, author, url, date, deletable)"
                            + " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            .text(record.id), .integer(Int64(position)), .text(item.key),
                            .text(item.direction?.rawValue), .text(item.author), .text(item.url), .text(item.date),
                            .bool(item.deletable),
                        ])
                }
            }
        }
    }

    func lastSynced() async throws -> String? {
        try database.transaction { db in
            try db.queryOne("SELECT value FROM desk_values WHERE name = ?", [.text(Self.lastSyncedName)])?.first?.string
        }
    }

    func setLastSynced(_ when: String) async throws {
        try database.transaction { db in
            try db.execute(
                "INSERT INTO desk_values (name, value) VALUES (?, ?)"
                    + " ON CONFLICT (name) DO UPDATE SET value = excluded.value",
                [.text(Self.lastSyncedName), .text(when)])
        }
    }
}
