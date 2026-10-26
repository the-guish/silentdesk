/// Rules about Jira: sites, the search, dates and topics.
/// See docs/specs/integrations/jira/jira.md.

import Foundation

enum JiraRules {
    static let service = "jira"
    /// The most recently updated open issues kept.
    static let syncCount = 10

    /// Accepts acme.atlassian.net, https://acme.atlassian.net/ or a Data
    /// Center address with a path, and returns https://host[:port][/path].
    /// Plain http is refused: tokens never travel unencrypted.
    static func normalizeSite(_ text: String) throws -> String {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URLComponents(string: text.contains("://") ? text : "https://\(text)") else {
            throw ConnectorError.auth(service, "The Jira site address is not valid.")
        }
        guard url.scheme?.lowercased() == "https" else {
            throw ConnectorError.auth(service, "The Jira site must use https://.")
        }
        guard let host = url.host?.lowercased(), !host.isEmpty, url.user == nil, url.password == nil else {
            throw ConnectorError.auth(service, "The Jira site address is not valid.")
        }
        var path = url.percentEncodedPath
        while path.hasSuffix("/") { path.removeLast() }
        return "https://\(host)" + (url.port.map { ":\($0)" } ?? "") + path
    }

    static func isCloudSite(_ site: String) -> Bool {
        (URLComponents(string: site)?.host ?? "").lowercased().hasSuffix(".atlassian.net")
    }

    static func accountLabel(_ account: JiraAccount) -> String {
        let site = account.endpoint.site
        let shown = site.hasPrefix("https://") ? String(site.dropFirst("https://".count)) : site
        return "\(account.userName) · \(shown)"
    }

    /// Jira writes dates like 2026-10-23T10:00:00.000+0200. Returns RFC 3339
    /// in UTC, or an empty string for anything else.
    static func rfc3339(_ text: String?) -> String {
        text.flatMap(RFC3339.fromISO8601) ?? ""
    }

    /// One topic per issue, with the issue as its one item: inbound when it is
    /// assigned to the user, outbound when the user is waiting on it.
    static func topic(_ issue: JiraIssue, account: JiraAccount) -> Topic {
        let assignedToMe = issue.assignee != nil && issue.assignee?.id == account.userID
        let reporter = issue.reporter?.name
        let item = Item(
            key: issue.key,
            direction: assignedToMe ? .inbound : .outbound,
            author: reporter?.isEmpty == false ? reporter : nil,
            url: "\(account.endpoint.site)/browse/\(issue.key)",
            date: rfc3339(issue.updated),
            // SilentDesk only reads Jira.
            deletable: false)
        let summary = issue.summary.trimmingCharacters(in: .whitespacesAndNewlines)
        return Topic(
            key: issue.issueID, title: summary.isEmpty ? issue.key : summary, items: [item], deletable: false,
            status: status(issue.status, category: issue.statusCategory))
    }

    /// Jira's status categories, by statusCategory.key. See
    /// docs/specs/topic-status.md.
    static let categories: [String: StatusCategory] = ["new": .new, "indeterminate": .inProgress, "done": .done]

    /// The issue's status, or nil when Jira gave it no name.
    static func status(_ name: String, category: String?) -> TopicStatus? {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        return TopicStatus(name: name, category: category.flatMap { categories[$0] })
    }
}
