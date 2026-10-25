/// Jira's REST API: Jira Cloud (email and API token, scoped or not) and Jira
/// Data Center (personal access token).

import Foundation

final class JiraHTTPAPI: JiraAPI {
    /// Open issues assigned to or reported by the user, most recently updated first.
    static let jql = "(assignee = currentUser() OR reporter = currentUser()) AND statusCategory != Done ORDER BY updated DESC"
    static let fields = "summary,status,assignee,reporter,updated,project"

    private let http: any Http
    private let service = JiraRules.service

    init(http: any Http) {
        self.http = http
    }

    private func authorization(_ credential: JiraCredential) -> String {
        if let email = credential.email, !email.isEmpty {
            return "Basic " + Base64.encode(Data("\(email):\(credential.token)".utf8))
        }
        return "Bearer \(credential.token)"
    }

    private func url(_ endpoint: JiraEndpoint, _ path: String) -> String {
        "\(endpoint.apiBase)/rest/api/\(endpoint.flavor == .cloud ? "3" : "2")/\(path)"
    }

    private func json(_ body: Data) -> JSON? {
        body.isEmpty ? nil : try? JSON.parse(body)
    }

    private func user(_ value: JSON?) -> JiraUser? {
        guard let value, value.object != nil else { return nil }
        let id = [value["accountId"], value["key"], value["name"]].lazy.compactMap { $0?.string }.first
        return JiraUser(id: id, name: value["displayName"]?.string ?? "")
    }

    private func issue(_ value: JSON) throws -> JiraIssue {
        guard let fields = value["fields"], fields.object != nil, let id = value["id"]?.string, let key = value["key"]?.string
        else { throw ConnectorError.network(service, "Jira's search answer could not be read.") }
        return JiraIssue(
            issueID: id,
            key: key,
            summary: fields["summary"]?.string ?? "",
            status: fields["status"]?["name"]?.string ?? "",
            project: fields["project"]?["key"]?.string ?? "",
            assignee: user(fields["assignee"]),
            reporter: user(fields["reporter"]),
            updated: fields["updated"]?.string)
    }

    private func get(_ url: String, _ credential: JiraCredential, params: [(String, String)] = []) async throws -> JSON {
        let response = try await http.request(
            "GET", url, headers: ["Accept": "application/json", "Authorization": authorization(credential)], params: params)
        let body = json(response.body)
        if response.status == 401 {
            throw ConnectorError.auth(service, "Jira rejected the token.")
        }
        guard response.isSuccess else {
            let message = body?["errorMessages"]?.array?.first?.string ?? body?["message"]?.string
            throw ConnectorError.remote(
                service, "Jira answered \(response.status): \(message ?? "no details").", status: response.status)
        }
        guard let body else { throw ConnectorError.network(service, "Jira's answer could not be read.") }
        return body
    }

    func myself(_ endpoint: JiraEndpoint, _ credential: JiraCredential) async throws -> JiraUser {
        guard let user = user(try await get(url(endpoint, "myself"), credential)) else {
            throw ConnectorError.network(service, "Jira's answer could not be read.")
        }
        return user
    }

    func cloudID(siteBase: String) async throws -> String? {
        let response = try await http.request("GET", "\(siteBase)/_edge/tenant_info")
        guard response.isSuccess else { return nil }
        return json(response.body)?["cloudId"]?.string
    }

    func openIssues(_ endpoint: JiraEndpoint, _ credential: JiraCredential, count: Int) async throws -> [JiraIssue] {
        // Jira Cloud replaced /search with /search/jql; Data Center keeps /search.
        let path = endpoint.flavor == .cloud ? "search/jql" : "search"
        let found = try await get(
            url(endpoint, path), credential,
            params: [("jql", Self.jql), ("maxResults", String(count)), ("fields", Self.fields)])
        guard let issues = (found["issues"] ?? .array([])).array else {
            throw ConnectorError.network(service, "Jira's search answer could not be read.")
        }
        return try issues.map(issue)
    }
}
