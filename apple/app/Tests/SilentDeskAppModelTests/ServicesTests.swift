import SilentDeskCore
import Testing

@testable import SilentDeskAppModel

@Test func githubAndJiraConnectWithAForm() {
    #expect(Services.fields("github").map(\.name) == ["token", "server"])
    #expect(Services.fields("jira").map(\.name) == ["site", "email", "token"])
    #expect(Services.fields("gmail").isEmpty)
    #expect(Services.fields("jira").filter(\.secret).map(\.name) == ["token"])
}

@Test func requiredFieldsMustBeFilledIn() {
    #expect(Services.missing("jira", ["site": " ", "email": ""]) == ["Site, such as acme.atlassian.net", "API token"])
    #expect(Services.missing("github", ["token": "t"]).isEmpty)
    #expect(Services.missing("gmail", [:]).isEmpty)
}

@Test func connectParamsAreTrimmedWithoutEmptyOptionalFields() {
    #expect(Services.connectParams("github", ["token": " t ", "server": "  "]) == ["token": "t"])
    #expect(Services.connectParams("jira", ["site": "a", "email": "e", "token": "t", "other": "x"])
        == ["site": "a", "email": "e", "token": "t"])
}

@Test func statusesReadAsOneLine() {
    func status(_ service: String, configured: Bool = true, connected: Bool = false, account: String? = nil) -> ServiceStatus {
        ServiceStatus(service: service, configured: configured, connected: connected, account: account)
    }
    #expect(Services.describe(status("gmail", connected: true, account: "a@b.c")) == "a@b.c")
    #expect(Services.describe(status("github", connected: true)) == "Connected")
    #expect(Services.describe(status("gmail", configured: false)) == "Set SILENTDESK_GOOGLE_CLIENT_ID to connect")
    #expect(Services.describe(status("github", configured: false)) == "Not set up")
    #expect(Services.describe(status("slack")) == "Not connected · signs in through your browser")
    #expect(Services.describe(status("jira")) == "Not connected")
}

@Test func gmailMovesToTheTrashAndOthersDelete() {
    #expect(Services.deletion("gmail", .topic).heading == "Move this thread to the trash?")
    #expect(Services.deletion("gmail", .item).done == "Moved to the trash")
    let task = Services.deletion("tasks", .topic)
    #expect(task.heading == "Delete this topic?")
    #expect(task.body == "SilentDesk deletes it in Google Tasks.")
    #expect(Services.deletion("slack", .item).heading == "Delete this message?")
}

@Test func onlyGmailReplies() {
    #expect(Services.canReply == ["gmail"])
}

@Test func clientIDsComeFromTheDefaultsWhenTheEnvironmentLacksThem() {
    let defaults: [String: Any] = [
        "SILENTDESK_GOOGLE_CLIENT_ID": "from-defaults",
        "SILENTDESK_SLACK_CLIENT_ID": "slack-defaults",
        "SILENTDESK_SLACK_REDIRECT_PORT": 5000,
        "SILENTDESK_TEST_KEYRING": "/tmp/keyring",
    ]
    let merged = AppSettings.environment(
        ["SILENTDESK_SLACK_CLIENT_ID": "slack-env", "SILENTDESK_GOOGLE_CLIENT_SECRET": ""]) { defaults[$0] }
    #expect(merged["SILENTDESK_GOOGLE_CLIENT_ID"] == "from-defaults")
    #expect(merged["SILENTDESK_SLACK_CLIENT_ID"] == "slack-env", "the environment wins")
    #expect(merged["SILENTDESK_SLACK_REDIRECT_PORT"] == "5000")
    #expect(merged["SILENTDESK_GOOGLE_CLIENT_SECRET"] == "")
    #expect(merged["SILENTDESK_TEST_KEYRING"] == nil, "test variables stay in the environment")
}
