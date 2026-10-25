/// GitHub's REST API. Works with github.com and GitHub Enterprise Server.
final class GitHubHTTPAPI: GitHubAPI {
    static let apiVersion = "2022-11-28"
    /// Most open pull requests kept per query. Search pages hold up to 100.
    static let perQuery = "50"

    private let http: any Http
    private let service = GitHubRules.service

    init(http: any Http) {
        self.http = http
    }

    private func get(_ url: String, token: String, params: [(String, String)] = []) async throws -> JSON {
        let response = try await http.request(
            "GET", url,
            headers: [
                "Authorization": "Bearer \(token)",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": Self.apiVersion,
            ],
            params: params)
        let body = response.body.isEmpty ? nil : try? JSON.parse(response.body)
        if response.status == 401 {
            throw ConnectorError.auth(service, "GitHub rejected the token. Check it, and its expiry.")
        }
        guard response.isSuccess else {
            let message = body?["message"]?.string
            throw ConnectorError.remote(
                service, "GitHub answered \(response.status): \(message ?? "no details").", status: response.status)
        }
        guard let body else { throw ConnectorError.network(service, "GitHub's answer could not be read.") }
        return body
    }

    func me(apiBase: String, token: String) async throws -> GitHubMe {
        do {
            let user = try await get("\(apiBase)/user", token: token)
            let name = user["name"]?.string
            return GitHubMe(login: try string(user, "login"), name: name?.isEmpty == false ? name : nil)
        } catch let error as ConnectorError where error.kind == .remote && error.status == 404 {
            throw ConnectorError.auth(service, "No GitHub API was found there. Check the server address.")
        }
    }

    func search(apiBase: String, token: String, query: String, reason: GitHubReason) async throws -> [PullRequest] {
        let found = try await get(
            "\(apiBase)/search/issues", token: token,
            params: [("q", query), ("sort", "updated"), ("order", "desc"), ("per_page", Self.perQuery)])
        guard let items = (found["items"] ?? .array([])).array else {
            throw ConnectorError.network(service, "GitHub's search answer could not be read.")
        }
        return try items.map { try pullRequest($0, reason: reason) }
    }

    private func string(_ value: JSON, _ key: String) throws -> String {
        guard let text = value[key]?.string else {
            throw ConnectorError.network(service, "GitHub's answer has no \(key).")
        }
        return text
    }

    private func pullRequest(_ item: JSON, reason: GitHubReason) throws -> PullRequest {
        guard item.object != nil, let id = item["id"]?.int, let number = item["number"]?.int else {
            throw ConnectorError.network(service, "GitHub's search answer could not be read.")
        }
        // https://api.github.com/repos/acme/web -> acme/web
        let repositoryURL = try string(item, "repository_url")
        let repo = repositoryURL.range(of: "/repos/").map { String(repositoryURL[$0.upperBound...]) } ?? repositoryURL
        return PullRequest(
            prID: id,
            repo: repo,
            number: number,
            title: item["title"]?.string ?? "",
            reason: reason,
            author: item["user"]?["login"]?.string ?? "",
            draft: item["draft"]?.bool == true,
            url: try string(item, "html_url"),
            updated: item["updated_at"]?.string ?? "")
    }
}
