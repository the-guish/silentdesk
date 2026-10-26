/// The Jira app's table: jira_state (spec/sql/).
final class JiraSqlcipherStateStore: JiraStateStore {
    private let database: any Database

    init(database: any Database) {
        self.database = database
    }

    func load() async throws -> JiraAccount? {
        try database.transaction { db in
            guard let row = try db.queryOne("SELECT user_id, user_name, site, api_base, flavor FROM jira_state WHERE id = 1")
            else { return nil }
            return JiraAccount(
                userID: row[0].string ?? "",
                userName: row[1].string ?? "",
                endpoint: JiraEndpoint(
                    site: row[2].string ?? "", apiBase: row[3].string ?? "",
                    flavor: JiraFlavor(rawValue: row[4].string ?? "") ?? .cloud))
        }
    }

    func save(_ account: JiraAccount) async throws {
        try database.transaction { db in
            try db.execute(
                "INSERT INTO jira_state (id, user_id, user_name, site, api_base, flavor) VALUES (1, ?, ?, ?, ?, ?)"
                    + " ON CONFLICT (id) DO UPDATE SET user_id = excluded.user_id, user_name = excluded.user_name,"
                    + " site = excluded.site, api_base = excluded.api_base, flavor = excluded.flavor",
                [
                    .text(account.userID), .text(account.userName), .text(account.endpoint.site),
                    .text(account.endpoint.apiBase), .text(account.endpoint.flavor.rawValue),
                ])
        }
    }

    func clear() async throws {
        try database.transaction { db in
            try db.execute("DELETE FROM jira_state")
        }
    }
}
