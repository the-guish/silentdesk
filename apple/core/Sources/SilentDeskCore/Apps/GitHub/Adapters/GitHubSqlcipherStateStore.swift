/// The GitHub app's table: github_state (spec/sql/).
final class GitHubSqlcipherStateStore: GitHubStateStore {
    private let database: any Database

    init(database: any Database) {
        self.database = database
    }

    func load() async throws -> GitHubAccount? {
        try database.transaction { db in
            guard let row = try db.queryOne("SELECT login, name, api_base, web_base FROM github_state WHERE id = 1") else {
                return nil
            }
            return GitHubAccount(
                login: row[0].string ?? "", name: row[1].string ?? "",
                endpoint: GitHubEndpoint(apiBase: row[2].string ?? "", webBase: row[3].string ?? ""))
        }
    }

    func save(_ account: GitHubAccount) async throws {
        try database.transaction { db in
            try db.execute(
                "INSERT INTO github_state (id, login, name, api_base, web_base) VALUES (1, ?, ?, ?, ?)"
                    + " ON CONFLICT (id) DO UPDATE SET login = excluded.login, name = excluded.name,"
                    + " api_base = excluded.api_base, web_base = excluded.web_base",
                [.text(account.login), .text(account.name), .text(account.endpoint.apiBase), .text(account.endpoint.webBase)])
        }
    }

    func clear() async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM github_state")
        }
    }
}
