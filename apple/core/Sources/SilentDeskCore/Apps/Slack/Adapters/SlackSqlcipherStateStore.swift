/// The Slack app's table: slack_state (spec/sql/).
final class SlackSqlcipherStateStore: SlackStateStore {
    private let database: any Database

    init(database: any Database) {
        self.database = database
    }

    func load() async throws -> SlackAccount? {
        try database.transaction { db in
            try db.queryOne("SELECT user_id, user_name, team_id, team_name FROM slack_state WHERE id = 1").map {
                SlackAccount(
                    userID: $0[0].string ?? "", userName: $0[1].string ?? "", teamID: $0[2].string ?? "",
                    teamName: $0[3].string ?? "")
            }
        }
    }

    func save(_ account: SlackAccount) async throws {
        try database.transaction { db in
            try db.execute(
                "INSERT INTO slack_state (id, user_id, user_name, team_id, team_name) VALUES (1, ?, ?, ?, ?)"
                    + " ON CONFLICT (id) DO UPDATE SET user_id = excluded.user_id, user_name = excluded.user_name,"
                    + " team_id = excluded.team_id, team_name = excluded.team_name",
                [.text(account.userID), .text(account.userName), .text(account.teamID), .text(account.teamName)])
        }
    }

    func clear() async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM slack_state")
        }
    }
}
