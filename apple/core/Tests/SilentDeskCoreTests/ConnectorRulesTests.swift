// The pure rules of each connector app; their HTTP behaviour is covered by
// the conformance suite.
import Foundation
@testable import SilentDeskCore
import Testing

// MARK: GitHub

@Test func gitHubServersAreNormalized() throws {
    #expect(try GitHubRules.endpoint(forServer: nil) == GitHubRules.githubCom)
    #expect(try GitHubRules.endpoint(forServer: "  ") == GitHubRules.githubCom)
    #expect(try GitHubRules.endpoint(forServer: "github.com") == GitHubRules.githubCom)
    #expect(try GitHubRules.endpoint(forServer: "https://api.github.com/") == GitHubRules.githubCom)
    let enterprise = try GitHubRules.endpoint(forServer: "GitHub.Acme.com")
    #expect(enterprise == GitHubEndpoint(apiBase: "https://github.acme.com/api/v3", webBase: "https://github.acme.com"))
    #expect(try GitHubRules.endpoint(forServer: "https://ghe.acme.com:8443/anything").apiBase == "https://ghe.acme.com:8443/api/v3")
    #expect(GitHubRules.host(enterprise) == "github.acme.com")
    #expect(throws: ConnectorError.self) { try GitHubRules.endpoint(forServer: "http://github.acme.com") }
    #expect(throws: ConnectorError.self) { try GitHubRules.endpoint(forServer: "https://user:pw@github.acme.com") }
    #expect(throws: ConnectorError.self) { try GitHubRules.endpoint(forServer: "https://") }
}

private func pull(_ id: Int, _ reason: GitHubReason, updated: String, title: String = "T") -> PullRequest {
    PullRequest(
        prID: id, repo: "acme/web", number: id, title: title, reason: reason, author: "bo", draft: false,
        url: "https://github.com/acme/web/pull/\(id)", updated: updated)
}

@Test func gitHubMergeKeepsTheStrongestReasonAndSortsByUpdate() {
    let found = [
        pull(1, .reviewRequested, updated: "2026-10-01T00:00:00Z"),
        pull(2, .assigned, updated: "2026-10-03T00:00:00Z"),
        pull(1, .assigned, updated: "2026-10-01T00:00:00Z"),
        pull(3, .authored, updated: "2026-10-03T00:00:00Z"),
    ]
    let merged = GitHubRules.merge(found)
    #expect(merged.map(\.prID) == [2, 3, 1])
    #expect(merged[2].reason == .reviewRequested)
    let topic = GitHubRules.topic(pull(9, .authored, updated: "2026-10-04T00:00:00Z", title: "  "))
    #expect(topic.title == "acme/web#9")
    #expect(topic.items[0].direction == .outbound)
    #expect(!topic.deletable)
}
