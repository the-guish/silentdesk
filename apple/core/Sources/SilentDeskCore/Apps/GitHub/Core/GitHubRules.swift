/// Rules about GitHub: which server, which pull requests, and their topics.
/// See docs/specs/integrations/github.md.

import Foundation

enum GitHubRules {
    static let service = "github"
    static let githubCom = GitHubEndpoint(apiBase: "https://api.github.com", webBase: "https://github.com")

    /// Open pull requests that ask something of the user, then the user's own.
    /// Each query must name `is:pr`: GitHub's search rejects queries without a
    /// type. `review-requested` includes requests made to the user's teams.
    static let queries: [(query: String, reason: GitHubReason)] = [
        ("is:pr is:open archived:false review-requested:@me", .reviewRequested),
        ("is:pr is:open archived:false assignee:@me", .assigned),
        ("is:pr is:open archived:false author:@me", .authored),
    ]

    /// No server means github.com. Otherwise a GitHub Enterprise Server host,
    /// such as github.acme.com; plain http is refused.
    static func endpoint(forServer server: String?) throws -> GitHubEndpoint {
        let server = (server ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if server.isEmpty {
            return githubCom
        }
        guard let url = URLComponents(string: server.contains("://") ? server : "https://\(server)") else {
            throw ConnectorError.auth(service, "The GitHub server address is not valid.")
        }
        guard url.scheme?.lowercased() == "https" else {
            throw ConnectorError.auth(service, "The GitHub server must use https://.")
        }
        guard let host = url.host?.lowercased(), !host.isEmpty, url.user == nil, url.password == nil else {
            throw ConnectorError.auth(service, "The GitHub server address is not valid.")
        }
        if host == "github.com" || host == "api.github.com" {
            return githubCom
        }
        let webBase = "https://\(host)" + (url.port.map { ":\($0)" } ?? "")
        return GitHubEndpoint(apiBase: "\(webBase)/api/v3", webBase: webBase)
    }

    static func host(_ endpoint: GitHubEndpoint) -> String {
        endpoint.webBase.hasPrefix("https://") ? String(endpoint.webBase.dropFirst("https://".count)) : endpoint.webBase
    }

    static func accountLabel(_ account: GitHubAccount) -> String {
        "\(account.login) · \(host(account.endpoint))"
    }

    static func direction(_ reason: GitHubReason) -> Direction {
        reason == .authored ? .outbound : .inbound
    }

    /// One entry per pull request, most recently updated first. When a pull
    /// request matches several queries, the first reason found wins: a review
    /// request outranks an assignment, which outranks authorship.
    static func merge(_ found: [PullRequest]) -> [PullRequest] {
        var byID: [Int: PullRequest] = [:]
        for pull in found where byID[pull.prID] == nil {
            byID[pull.prID] = pull
        }
        return byID.values.sorted { first, second in
            first.updated != second.updated ? first.updated > second.updated : first.prID < second.prID
        }
    }

    /// One topic per pull request, with the pull request as its one item.
    static func topic(_ pull: PullRequest) -> Topic {
        let item = Item(
            key: String(pull.prID),
            direction: direction(pull.reason),
            author: pull.author.isEmpty ? nil : pull.author,
            url: pull.url,
            date: pull.updated,
            // SilentDesk only reads GitHub.
            deletable: false)
        let title = pull.title.trimmingCharacters(in: .whitespacesAndNewlines)
        return Topic(
            key: String(pull.prID), title: title.isEmpty ? "\(pull.repo)#\(pull.number)" : title, items: [item],
            deletable: false)
    }
}
