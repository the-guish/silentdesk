/// GitHub's REST and GraphQL APIs. Works with github.com and GitHub
/// Enterprise Server.
final class GitHubHTTPAPI: GitHubAPI {
    static let apiVersion = "2022-11-28"
    /// Most open pull requests kept per query. Search pages hold up to 100.
    static let perQuery = 50
    /// One search per reason, each named after it, with what the chip needs.
    static let pullRequests = """
        query($reviewRequested: String!, $assigned: String!, $authored: String!, $first: Int!) {
          reviewRequested: search(query: $reviewRequested, type: ISSUE, first: $first) { ...pulls }
          assigned: search(query: $assigned, type: ISSUE, first: $first) { ...pulls }
          authored: search(query: $authored, type: ISSUE, first: $first) { ...pulls }
        }
        fragment pulls on SearchResultItemConnection {
          nodes {
            ... on PullRequest {
              databaseId number title url updatedAt isDraft state merged reviewDecision
              author { login }
              repository { nameWithOwner }
              commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
            }
          }
        }
        """

    private let http: any Http
    private let service = GitHubRules.service

    init(http: any Http) {
        self.http = http
    }

    private func send(_ method: String, _ url: String, token: String, json: JSON? = nil) async throws -> JSON {
        let response = try await http.request(
            method, url,
            headers: [
                "Authorization": "Bearer \(token)",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": Self.apiVersion,
            ],
            json: json)
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
            let user = try await send("GET", "\(apiBase)/user", token: token)
            let name = user["name"]?.string
            return GitHubMe(login: try string(user, "login"), name: name?.isEmpty == false ? name : nil)
        } catch let error as ConnectorError where error.kind == .remote && error.status == 404 {
            throw ConnectorError.auth(service, "No GitHub API was found there. Check the server address.")
        }
    }

    func openPullRequests(
        graphqlURL: String, token: String, queries: [(query: String, reason: GitHubReason)]
    ) async throws -> GitHubFound {
        var variables: [String: JSON] = ["first": .int(Int64(Self.perQuery))]
        for (query, reason) in queries {
            variables[reason.rawValue] = .string(query)
        }
        let found = try await send(
            "POST", graphqlURL, token: token, json: ["query": .string(Self.pullRequests), "variables": .object(variables)])
        // GitHub can answer with data and errors at once, such as for a
        // repository the token cannot read. Its pull requests come back
        // empty, and the answer is partial: the others still count, and the
        // unread ones keep their topics. A missing search fails the sync.
        var pulls: [PullRequest] = []
        for (_, reason) in queries {
            guard let nodes = found["data"]?[reason.rawValue]?["nodes"]?.array else {
                if let first = found["errors"]?.array?.first {
                    throw ConnectorError.remote(
                        service, "GitHub answered: \(first["message"]?.string ?? "an error").", status: 200)
                }
                throw ConnectorError.network(service, "GitHub's search answer could not be read.")
            }
            // A search for pull requests can still hold an empty node, as for
            // a repository the token cannot read.
            for node in nodes where node.object?.isEmpty == false {
                pulls.append(try pullRequest(node, reason: reason))
            }
        }
        return GitHubFound(pulls: pulls, complete: found["errors"]?.array?.isEmpty ?? true)
    }

    private func string(_ value: JSON, _ key: String) throws -> String {
        guard let text = value[key]?.string else {
            throw ConnectorError.network(service, "GitHub's answer has no \(key).")
        }
        return text
    }

    private func pullRequest(_ node: JSON, reason: GitHubReason) throws -> PullRequest {
        guard node.object != nil, let id = node["databaseId"]?.int, let number = node["number"]?.int else {
            throw ConnectorError.network(service, "GitHub's search answer could not be read.")
        }
        let state = node["state"]?.string
        return PullRequest(
            prID: id,
            repo: node["repository"]?["nameWithOwner"]?.string ?? "",
            number: number,
            title: node["title"]?.string ?? "",
            reason: reason,
            author: node["author"]?["login"]?.string ?? "",
            draft: node["isDraft"]?.bool == true,
            url: try string(node, "url"),
            updated: node["updatedAt"]?.string ?? "",
            merged: node["merged"]?.bool == true,
            closed: state == "CLOSED" || state == "MERGED",
            // The state GitHub sums up for the checks on the last commit.
            checks: node["commits"]?["nodes"]?.array?.last?["commit"]?["statusCheckRollup"]?["state"]?.string,
            review: node["reviewDecision"]?.string)
    }
}
