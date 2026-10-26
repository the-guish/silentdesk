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

@Test(arguments: [
    ("To Do", "new", TopicStatus(name: "To Do", category: .new)),
    ("Code Review", "indeterminate", TopicStatus(name: "Code Review", category: .inProgress)),
    ("Closed", "done", TopicStatus(name: "Closed", category: .done)),
    ("Triage", "undefined", TopicStatus(name: "Triage", category: nil)),
    ("Triage", nil, TopicStatus(name: "Triage", category: nil)),
    (" In Progress ", "indeterminate", TopicStatus(name: "In Progress", category: .inProgress)),
    ("", "new", nil),
] as [(String, String?, TopicStatus?)])
func jiraStatusesKeepTheirNameAndMapTheirCategory(_ name: String, _ category: String?, _ expected: TopicStatus?) {
    #expect(JiraRules.status(name, category: category) == expected)
}

@Test func jiraIssuesBecomeTopics() {
    let account = JiraAccount(
        userID: "acc-ana", userName: "Ana",
        endpoint: JiraEndpoint(site: "https://acme.atlassian.net", apiBase: "https://acme.atlassian.net", flavor: .cloud))
    let mine = JiraIssue(
        issueID: "1", key: "PAY-1", summary: " Refund ", status: "Open", project: "PAY",
        assignee: JiraUser(id: "acc-ana", name: "Ana"), reporter: JiraUser(id: "acc-bo", name: "Bo"),
        updated: "2026-10-23T10:00:00.000+0200", statusCategory: "new")
    let topic = JiraRules.topic(mine, account: account)
    #expect(topic.title == "Refund")
    #expect(topic.status == TopicStatus(name: "Open", category: .new))
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
    #expect(waiting.status == nil, "an issue without a status name has none")
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

// MARK: Gmail

@Test func gmailSenderNames() {
    #expect(GmailRules.senderName("Ana Ruiz <ana@example.com>") == "Ana Ruiz")
    #expect(GmailRules.senderName("\"Ruiz, Ana\" <ana@example.com>") == "Ruiz, Ana")
    #expect(GmailRules.senderName("<ana@example.com>") == "ana@example.com")
    #expect(GmailRules.senderName("ana@example.com") == "ana@example.com")
    #expect(GmailRules.senderName("") == "")
}

@Test func gmailRepliesAnswerTheSenderWithThreadingHeaders() throws {
    let original = GmailOriginal(
        direction: .inbound, sender: "Bo Lind <bo@acme.com>", to: "ana@example.com", replyTo: "", subject: "Invoice",
        headerID: "<m1@mail.example>", references: "<m0@mail.example>")
    let reply = GmailRules.reply(original, body: "Thanks,\nit's paid.")
    let lines = reply.components(separatedBy: "\r\n")
    #expect(lines[0] == "To: Bo Lind <bo@acme.com>")
    #expect(lines[1] == "Subject: Re: Invoice")
    #expect(lines[2] == "In-Reply-To: <m1@mail.example>")
    #expect(lines[3] == "References: <m0@mail.example> <m1@mail.example>")
    #expect(lines[4] == "MIME-Version: 1.0")
    #expect(lines[5] == "Content-Type: text/plain; charset=UTF-8")
    #expect(lines[6] == "Content-Transfer-Encoding: base64")
    #expect(lines[7] == "")
    let body = try #require(Data(base64Encoded: lines[8]))
    #expect(String(decoding: body, as: UTF8.self) == "Thanks,\r\nit's paid.")
    #expect(reply.hasSuffix("\r\n"))
}

@Test func gmailRepliesToSentMailGoToItsRecipientsAndEncodeSubjects() {
    let original = GmailOriginal(
        direction: .outbound, sender: "ana@example.com", to: "bo@acme.com, cy@acme.com", replyTo: "other@acme.com",
        subject: "re: Déjà vu\r\nX-Injected: yes", headerID: "", references: "")
    let reply = GmailRules.reply(original, body: "ok")
    let lines = reply.components(separatedBy: "\r\n")
    #expect(lines[0] == "To: bo@acme.com, cy@acme.com")
    #expect(lines[1] == "Subject: =?UTF-8?B?\(Base64.encode(Data("re: Déjà vu X-Injected: yes".utf8)))?=")
    #expect(!reply.contains("In-Reply-To"), "no Message-ID, no threading headers")
    #expect(GmailRules.replySubject("") == "Re:")
    #expect(GmailRules.replySubject("RE: x") == "RE: x")
    #expect(GmailRules.recipient(GmailOriginal(
        direction: .inbound, sender: "s", to: "t", replyTo: " r ", subject: "", headerID: "", references: "")) == " r ")
}

@Test func gmailLongBodiesWrapAt76Characters() {
    let original = GmailOriginal(direction: .inbound, sender: "s", to: "t", replyTo: "", subject: "", headerID: "", references: "")
    let reply = GmailRules.reply(original, body: String(repeating: "x", count: 200))
    let encoded = reply.components(separatedBy: "\r\n\r\n")[1].components(separatedBy: "\r\n").filter { !$0.isEmpty }
    #expect(encoded.count == 4)
    #expect(encoded.dropLast().allSatisfy { $0.count == 76 })
}

@Test func gmailThreadsBecomeTopicsOldestFirst() {
    let messages = [
        GmailMessage(messageID: "m2", threadID: "t1", direction: .inbound, sender: "Bo <bo@x>", subject: "Re: Hi", date: "2025-10-24T11:00:00Z"),
        GmailMessage(messageID: "m1", threadID: "t1", direction: .outbound, sender: "ana@x", subject: "  Hi ", date: "2025-10-24T10:00:00Z"),
    ]
    let topic = GmailRules.topic(threadID: "t1", messages: messages)
    #expect(topic.title == "Hi")
    #expect(topic.items.map(\.key) == ["m1", "m2"])
    #expect(topic.items[0].author == "ana@x")
    #expect(topic.items[1].author == "Bo")
    #expect(topic.items[0].url == "https://mail.google.com/mail/#all/t1")
    #expect(topic.deletable && topic.items.allSatisfy(\.deletable))
    #expect(GmailRules.topic(threadID: "t", messages: [
        GmailMessage(messageID: "m", threadID: "t", direction: .inbound, sender: "", subject: " ", date: "d")
    ]).title == "(no subject)")
    #expect(GmailRules.newIDs(known: ["a"], ["b", "a", "c", "b"]) == ["b", "c"])
    #expect(GmailHTTPAPI.isGmailID("18c2abc"))
    #expect(!GmailHTTPAPI.isGmailID("../x"))
    #expect(!GmailHTTPAPI.isGmailID(""))
    #expect(GmailHTTPAPI.date(.string("1761300000000")) == "2025-10-24T10:00:00Z")
    #expect(GmailHTTPAPI.date(.string("soon")) == nil)
    #expect(GmailHTTPAPI.date(nil) == nil)
}

// MARK: Slack

@Test func slackMarkupBecomesPlainText() {
    let names = ["U2": "Bo", "U9": ""]
    #expect(SlackRules.plainText("On it, <@U2>", names: names) == "On it, @Bo")
    #expect(SlackRules.plainText("<@U9|bo9> and <@U3>", names: names) == "@bo9 and @someone")
    #expect(SlackRules.plainText("Can you check <https://x.example/deploy|the deploy>?", names: [:]) == "Can you check the deploy?")
    #expect(SlackRules.plainText("See <https://x.example>", names: [:]) == "See https://x.example")
    #expect(SlackRules.plainText("In <#C1|general> <!here> <!subteam^S1|@ops>", names: [:]) == "In #general @here @@ops")
    #expect(SlackRules.plainText("a &lt;b&gt; &amp; c", names: [:]) == "a <b> & c")
    #expect(SlackRules.plainText("unterminated <tag", names: [:]) == "unterminated <tag")
}

@Test func slackPreviewsCollapseAndCut() {
    #expect(SlackRules.preview("  Lunch\n at  1? ") == "Lunch at 1?")
    #expect(SlackRules.preview("one two three four", limit: 10) == "one two…")
    #expect(SlackRules.preview("abcdefghijklmnop", limit: 5) == "abcde…")
    #expect(SlackRules.mentionIDs("<@U2> hi <@U1|ana> <@U2>") == ["U1", "U2"])
    #expect(SlackRules.mentionIDs("none") == [])
    #expect(SlackRules.rfc3339(ts: "1761300000.000100") == "2025-10-24T10:00:00Z")
    #expect(SlackRules.rfc3339(ts: "junk") == "1970-01-01T00:00:00Z")
}

private func match(_ channel: String, _ ts: String, im: Bool = true, mpim: Bool = false) -> SlackMatch {
    SlackMatch(channelID: channel, channelName: "U2", isIM: im, isMPIM: mpim, user: "U2", username: nil, text: "t", ts: ts, permalink: "")
}

@Test func slackKeepsRecentDirectMessagesOnly() {
    let found = [
        match("D1", "100.1"), match("C1", "999.0", im: false), match("G1", "300.1", im: false, mpim: true),
        match("D1", "100.1"), match("D1", "200.1"),
    ]
    #expect(SlackRules.selectRecent(found, count: 2).map(\.ts) == ["300.1", "200.1"])
    #expect(SlackRules.selectRecent(found, count: 10).map(\.ts) == ["300.1", "200.1", "100.1"])
}

@Test func slackConversationsBecomeTopics() {
    let messages = [
        SlackDirectMessage(channelID: "D1", ts: "200.1", direction: .outbound, author: "Ana", counterpart: "Bo", preview: "On it", permalink: "p2", date: "d2"),
        SlackDirectMessage(channelID: "G1", ts: "300.1", direction: .inbound, author: "Cy", counterpart: "Group DM", preview: "", permalink: "", date: "d3"),
        SlackDirectMessage(channelID: "D1", ts: "100.1", direction: .inbound, author: "Bo", counterpart: "Bo", preview: "Hi", permalink: "p1", date: "d1"),
    ]
    let topics = SlackRules.topics(messages)
    #expect(topics.map(\.key) == ["D1", "G1"])
    #expect(topics[0].title == "On it")
    #expect(topics[0].items.map(\.key) == ["100.1", "200.1"])
    #expect(topics[1].title == "(empty message)")
    #expect(topics[1].items[0].url == nil)
    #expect(!topics[0].deletable)
}

@Test func slackTokensRefreshBeforeExpiry() {
    let rotating = SlackCredential(accessToken: "a", refreshToken: "r", expiresAt: 1_000)
    #expect(SlackRules.needsRefresh(rotating, now: 940))
    #expect(!SlackRules.needsRefresh(rotating, now: 939))
    #expect(!SlackRules.needsRefresh(SlackCredential(accessToken: "a", refreshToken: nil, expiresAt: 1_000), now: 2_000))
    #expect(!SlackRules.needsRefresh(SlackCredential(accessToken: "a", refreshToken: "r", expiresAt: nil), now: 2_000))
}

// MARK: Credentials

@Test func credentialsHideTheirTokensWhenPrinted() {
    #expect(!"\(GmailGrant(accessToken: "a-secret", refreshToken: "r-secret"))".contains("secret"))
    #expect(!"\(GoogleTasksGrant(accessToken: "a-secret", refreshToken: "r-secret"))".contains("secret"))
    #expect(!"\(SlackCredential(accessToken: "xoxp-secret", refreshToken: "xoxe-secret", expiresAt: 10))".contains("secret"))
    #expect(!"\(JiraCredential(email: "ana@acme.com", token: "jira-secret"))".contains("secret"))
}
