/// The Google Tasks app's table: google_tasks_state (spec/sql/).
final class TasksSqlcipherStateStore: TasksStateStore {
    private let database: any Database

    init(database: any Database) {
        self.database = database
    }

    func load(_ service: String) async throws -> GoogleTasksState? {
        try database.transaction { db in
            try db.queryOne("SELECT email FROM google_tasks_state WHERE service = ?", [.text(service)])
                .map { GoogleTasksState(email: $0[0].string ?? "") }
        }
    }

    func save(_ service: String, _ state: GoogleTasksState) async throws {
        try database.transaction { db in
            try db.execute(
                "INSERT INTO google_tasks_state (service, email) VALUES (?, ?)"
                    + " ON CONFLICT (service) DO UPDATE SET email = excluded.email",
                [.text(service), .text(state.email)])
        }
    }

    func clear(_ service: String) async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM google_tasks_state WHERE service = ?", [.text(service)])
        }
    }
}
