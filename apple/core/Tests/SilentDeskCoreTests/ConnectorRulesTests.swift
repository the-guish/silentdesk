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

// MARK: Jira

@Test func jiraSitesAreNormalized() throws {
    #expect(try JiraRules.normalizeSite("acme.atlassian.net") == "https://acme.atlassian.net")
    #expect(try JiraRules.normalizeSite(" https://acme.atlassian.net/ ") == "https://acme.atlassian.net")
    #expect(try JiraRules.normalizeSite("jira.acme.com/jira/") == "https://jira.acme.com/jira")
    #expect(try JiraRules.normalizeSite("https://jira.acme.com:8443/jira") == "https://jira.acme.com:8443/jira")
    #expect(throws: ConnectorError.self) { try JiraRules.normalizeSite("http://jira.acme.com") }
    #expect(throws: ConnectorError.self) { try JiraRules.normalizeSite("") }
    #expect(JiraRules.isCloudSite("https://acme.atlassian.net"))
    #expect(!JiraRules.isCloudSite("https://jira.acme.com"))
}

@Test func jiraIssuesBecomeTopics() {
    let account = JiraAccount(
        userID: "acc-ana", userName: "Ana",
        endpoint: JiraEndpoint(site: "https://acme.atlassian.net", apiBase: "https://acme.atlassian.net", flavor: .cloud))
    let mine = JiraIssue(
        issueID: "1", key: "PAY-1", summary: " Refund ", status: "Open", project: "PAY",
        assignee: JiraUser(id: "acc-ana", name: "Ana"), reporter: JiraUser(id: "acc-bo", name: "Bo"),
        updated: "2026-10-23T10:00:00.000+0200")
    let topic = JiraRules.topic(mine, account: account)
    #expect(topic.title == "Refund")
    #expect(topic.key == "1")
    #expect(topic.items[0] == Item(
        key: "PAY-1", direction: .inbound, author: "Bo", url: "https://acme.atlassian.net/browse/PAY-1",
        date: "2026-10-23T08:00:00Z", deletable: false))
    let theirs = JiraIssue(
        issueID: "2", key: "WEB-7", summary: "", status: "", project: "", assignee: nil,
        reporter: JiraUser(id: nil, name: ""), updated: nil)
    let waiting = JiraRules.topic(theirs, account: account)
    #expect(waiting.title == "WEB-7")
    #expect(waiting.items[0].direction == .outbound)
    #expect(waiting.items[0].author == nil)
    #expect(waiting.items[0].date == "")
    #expect(JiraRules.accountLabel(account) == "Ana · acme.atlassian.net")
    #expect(JiraCredential(email: "a@b", token: "t").flavor == .cloud)
    #expect(JiraCredential(email: nil, token: "t").flavor == .dataCenter)
}

// MARK: Google Tasks

@Test func tasksBecomeTopics() {
    let task = GoogleTask(
        taskID: "t1", listID: "l", listTitle: "My Tasks", title: "  ", completed: false, deleted: false, due: nil,
        origin: nil, url: "https://tasks.google.com/", updated: "2026-10-20T08:00:00.000Z")
    let topic = TasksRules.topic(task)
    #expect(topic.title == "Untitled task")
    #expect(topic.items[0].direction == nil)
    #expect(TasksRules.isOpen(task))
    #expect(!TasksRules.isOpen(GoogleTask(
        taskID: "t2", listID: "l", listTitle: "", title: "Done", completed: true, deleted: false, due: nil, origin: nil,
        url: "", updated: "")))
}

// MARK: Credentials

@Test func credentialsHideTheirTokensWhenPrinted() {
    #expect(!"\(GoogleTasksGrant(accessToken: "a-secret", refreshToken: "r-secret"))".contains("secret"))
    #expect(!"\(JiraCredential(email: "ana@acme.com", token: "jira-secret"))".contains("secret"))
}
