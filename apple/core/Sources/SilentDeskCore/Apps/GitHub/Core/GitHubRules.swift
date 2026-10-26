/// Rules about GitHub: which server, which pull requests, and their topics.
/// See docs/specs/integrations/github/github.md.

import Foundation

enum GitHubRules {
    static let service = "github"
    static let githubCom = GitHubEndpoint(apiBase: "https://api.github.com", webBase: "https://github.com")

    /// Open pull requests that ask something of the user, then the user's own.
    /// Each query must name `is:pr`: GitHub's search rejects queries without a
    /// type. `review-requested` includes requests made to the user's teams.
    static let queries: [(query: String, reason: GitHubReason)] = [
        ("is:pr is:open archived:false review-requested:@me sort:updated-desc", .reviewRequested),
        ("is:pr is:open archived:false assignee:@me sort:updated-desc", .assigned),
        ("is:pr is:open archived:false author:@me sort:updated-desc", .authored),
    ]

    /// Each chip's category. See docs/specs/integrations/github/github-status.md.
    static let statusCategories: [String: StatusCategory] = [
        "Merged": .done,
        "Closed": .done,
        "CI Failed": .inProgress,
        "Approved": .inProgress,
        "Changes Requested": .inProgress,
        "In review": .inProgress,
        "Draft": .new,
    ]

    /// GitHub's GraphQL API, next to its REST API: /graphql on github.com,
    /// /api/graphql on GitHub Enterprise Server.
    static func graphqlURL(_ apiBase: String) -> String {
        apiBase.hasSuffix("/api/v3") ? String(apiBase.dropLast("/v3".count)) + "/graphql" : apiBase + "/graphql"
    }

    /// The pull request's chip: the first that applies wins.
    static func status(_ pull: PullRequest) -> TopicStatus {
        let name =
            if pull.merged { "Merged" }
            else if pull.closed { "Closed" }
            else if pull.checks == "FAILURE" || pull.checks == "ERROR" { "CI Failed" }
            else if pull.review == "APPROVED" { "Approved" }
            else if pull.review == "CHANGES_REQUESTED" { "Changes Requested" }
            else if !pull.draft { "In review" }
            else { "Draft" }
        return TopicStatus(name: name, category: statusCategories[name])
    }

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
            deletable: false, status: status(pull))
    }
}
