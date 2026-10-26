import Foundation
import SilentDeskCore
import Testing

@testable import SilentDeskAppModel

@MainActor
private func queue(_ desk: FakeDesk, clock: ManualClock = ManualClock()) -> QueueModel {
    QueueModel(desk: desk, clock: { clock.now })
}

// MARK: The queue

@Test @MainActor func loadShowsTheTopicsAndWhenTheyChanged() async {
    let desk = FakeDesk()
    await desk.set(topics: [topic("a"), topic("b")])
    await desk.set(synced: "2026-10-25T15:00:00Z")
    let model = queue(desk)
    #expect(model.content == .empty)
    await model.load()
    #expect(model.topics.map(\.id) == ["a", "b"])
    #expect(model.content == .list)
    #expect(model.status(now: Format.parse("2026-10-25T15:03:00Z")!) == "Updated 3 min ago")
}

@Test @MainActor func searchFiltersTheQueue() async {
    let desk = FakeDesk()
    await desk.set(topics: [topic("a", title: "Budget"), topic("b", title: "Certificates")])
    let model = queue(desk)
    await model.load()
    model.query = "budget"
    #expect(model.shown.map(\.id) == ["a"])
    model.query = "nothing"
    #expect(model.content == .noMatch)
    model.query = " "
    #expect(model.shown.count == 2)
}

@Test @MainActor func refreshSyncsEveryServiceThenLoads() async {
    let desk = FakeDesk()
    let model = queue(desk)
    await model.refresh()
    #expect(await desk.calls == ["sync all", "topics", "lastSynced"])
    #expect(!model.refreshing)
}

@Test @MainActor func aRefreshWhileOneRunsDoesNothing() async {
    let desk = FakeDesk()
    await desk.hold()
    let model = queue(desk)
    let first = Task { await model.refresh() }
    await eventually { await desk.waiting == 1 }
    #expect(model.refreshing)
    #expect(model.status(now: Date()) == "Refreshing…")
    await model.refresh()
    #expect(await desk.waiting == 1, "the second refresh did not start a round")
    await desk.release()
    await first.value
    #expect(await desk.calls.filter { $0.hasPrefix("sync") } == ["sync all"])
}

@Test @MainActor func aFailedRoundSaysWhyAndKeepsTheTopics() async {
    let desk = FakeDesk()
    await desk.set(topics: [topic("a")])
    let model = queue(desk)
    await model.load()
    await desk.fail("sync", with: ConnectorError.network("slack", "Offline."))
    await model.refresh()
    #expect(model.notices.current?.text == "Slack: Offline.")
    #expect(model.topics.map(\.id) == ["a"])
}

@Test @MainActor func comingBackSyncsOnlyAfterThirtySeconds() async {
    let desk = FakeDesk()
    let clock = ManualClock()
    let model = queue(desk, clock: clock)
    await model.becameActive()
    clock.now += 20
    await model.becameActive()
    #expect(await desk.calls.filter { $0.hasPrefix("sync") }.count == 1)
    clock.now += 11
    await model.becameActive()
    #expect(await desk.calls.filter { $0.hasPrefix("sync") }.count == 2)
}

@Test @MainActor func theSelectionClosesWhenItsTopicIsGone() async {
    let desk = FakeDesk()
    await desk.set(topics: [topic("a"), topic("b")])
    let model = queue(desk)
    await model.load()
    model.selection = "b"
    #expect(model.selectedTopic?.id == "b")
    await desk.set(topics: [topic("a")])
    await model.load()
    #expect(model.selection == nil)
}

@Test @MainActor func aConnectedServiceSyncsAndADisconnectedOneReloads() async {
    let desk = FakeDesk()
    let model = queue(desk)
    await model.serviceChanged("github", connected: true)
    await model.serviceChanged("github", connected: false)
    #expect(await desk.calls == ["sync github", "topics", "lastSynced", "topics", "lastSynced"])
}

@Test @MainActor func deletingTheOpenTopicClosesItAndSaysSo() async {
    let desk = FakeDesk()
    await desk.set(topics: [topic("a")])
    let model = queue(desk)
    await model.load()
    model.selection = "a"
    await model.deleted(topic("a"))
    #expect(model.selection == nil)
    #expect(model.notices.current?.text == "Moved to the trash")
}

// MARK: The topic screen

@Test @MainActor func itemsShowWithoutTextAndANote() async {
    let desk = FakeDesk()
    let shown = topic(
        "a", service: "github",
        items: [item("1", author: "octocat", url: "https://github.com/x", deletable: true), item("2", author: nil)])
    let model = TopicModel(topic: shown, desk: desk, notices: Notices())
    await model.loadHistory()
    #expect(model.messages == nil, "github keeps no conversation")
    #expect(model.notices.shown.isEmpty, "unsupported is not a failure")
    #expect(model.entries.map(\.who) == ["octocat", "GitHub"])
    #expect(model.entries.map(\.deletable) == [true, false])
    #expect(model.entries[0].url == "https://github.com/x")
    #expect(model.note?.contains("Open one in GitHub") == true)
    #expect(!model.canReply)
}

@Test @MainActor func aSingleItemIsDeletedThroughTheTopic() {
    let model = TopicModel(topic: topic("a", items: [item("1", deletable: true)]), desk: FakeDesk(), notices: Notices())
    #expect(model.entries.map(\.deletable) == [false])
}

@Test @MainActor func aConversationReplacesTheItems() async {
    let desk = FakeDesk()
    await desk.set(conversation: [
        Message(key: "m1", direction: .inbound, author: "Ana", text: "Hello", date: "2026-10-25T10:00:00Z"),
        Message(key: "m2", direction: .outbound, author: nil, text: "Hi", date: "2026-10-25T11:00:00Z"),
    ])
    let model = TopicModel(topic: topic("a"), desk: desk, notices: Notices())
    await model.loadHistory()
    #expect(model.entries.map(\.text) == ["Hello", "Hi"])
    #expect(model.entries.map(\.who) == ["Ana", "Gmail"])
    #expect(model.note == nil)
    #expect(model.canReply)
}

@Test @MainActor func aFailedHistorySaysWhy() async {
    let desk = FakeDesk()
    await desk.fail("history", with: ConnectorError.auth("slack", "Sign in again."))
    let model = TopicModel(topic: topic("a", service: "slack"), desk: desk, notices: Notices())
    await model.loadHistory()
    #expect(model.notices.current?.text == "Slack: Sign in again.")
    #expect(!model.loading)
}

@Test @MainActor func aReplyIsSentThenClearedAndTheServiceSyncs() async {
    let desk = FakeDesk()
    let model = TopicModel(topic: topic("a"), desk: desk, notices: Notices())
    var replied: [String] = []
    model.replied = { replied.append($0.id) }
    #expect(!model.canSend)
    model.reply = "  "
    #expect(!model.canSend)
    model.reply = "Thanks!"
    await model.send()
    #expect(await desk.calls == ["reply a Thanks!"])
    #expect(model.reply == "")
    #expect(model.notices.current?.text == "Reply sent")
    #expect(replied == ["a"])
}

@Test @MainActor func aFailedReplyKeepsTheText() async {
    let desk = FakeDesk()
    await desk.fail("reply", with: ConnectorError.remote("gmail", "Quota."))
    let model = TopicModel(topic: topic("a"), desk: desk, notices: Notices())
    model.reply = "Thanks!"
    await model.send()
    #expect(model.reply == "Thanks!")
    #expect(!model.sending)
    #expect(model.notices.current?.text == "Gmail: Quota.")
}

@Test @MainActor func deletingTellsTheQueue() async {
    let desk = FakeDesk()
    let model = TopicModel(topic: topic("a"), desk: desk, notices: Notices())
    var told: [String] = []
    model.deleted = { told.append("topic \($0.id)") }
    model.itemDeleted = { told.append("item \($0.id)") }
    await model.deleteItem("a-1")
    await model.delete()
    #expect(await desk.calls == ["deleteItem a a-1", "delete a"])
    #expect(told == ["item a", "topic a"])
}

@Test @MainActor func aFailedDeleteKeepsTheTopic() async {
    let desk = FakeDesk()
    await desk.fail("delete", with: ConnectorError.remote("gmail", "Gone."))
    let model = TopicModel(topic: topic("a"), desk: desk, notices: Notices())
    var told = false
    model.deleted = { _ in told = true }
    await model.delete()
    #expect(!told)
    #expect(model.notices.current?.text == "Gmail: Gone.")
}

@Test @MainActor func showUpdatesTheTopic() {
    let model = TopicModel(topic: topic("a", title: "Old"), desk: FakeDesk(), notices: Notices())
    model.show(topic("a", title: "New"))
    #expect(model.topic.title == "New")
}

// MARK: Services

@Test @MainActor func connectingSendsTheFormThenForgetsIt() async {
    let desk = FakeDesk()
    let model = ServicesModel(desk: desk)
    var changed: [String] = []
    model.changed = { service, connected in changed.append("\(service) \(connected)") }
    model.set("github", "token", " secret ")
    await model.connect("github")
    #expect(await desk.calls == ["connect github token=secret", "services"])
    #expect(model.value("github", "token") == "")
    #expect(model.notices.current?.text == "Connected GitHub")
    #expect(changed == ["github true"])
}

@Test @MainActor func connectingAsksForMissingFields() async {
    let desk = FakeDesk()
    let model = ServicesModel(desk: desk)
    await model.connect("jira")
    #expect(await desk.calls.isEmpty)
    #expect(model.notices.current?.text == "Fill in: Site, such as acme.atlassian.net, API token.")
}

@Test @MainActor func aFailedConnectKeepsWhatWasTyped() async {
    let desk = FakeDesk()
    await desk.fail("connect", with: ConnectorError.auth("github", "Bad credentials."))
    let model = ServicesModel(desk: desk)
    model.set("github", "token", "wrong")
    await model.connect("github")
    #expect(model.value("github", "token") == "wrong")
    #expect(model.busy == nil)
    #expect(model.notices.current?.text == "GitHub: Bad credentials.")
}

@Test @MainActor func disconnectingTellsTheQueue() async {
    let desk = FakeDesk()
    let model = ServicesModel(desk: desk)
    var changed: [String] = []
    model.changed = { service, connected in changed.append("\(service) \(connected)") }
    await model.disconnect("slack")
    #expect(await desk.calls == ["disconnect slack", "services"])
    #expect(changed == ["slack false"])
}

// MARK: The demo desk

@Test @MainActor func theDemoDeskFillsEveryScreen() async throws {
    let desk = DemoDesk()
    let topics = try await desk.topics()
    #expect(topics.count >= 5)
    #expect(Set(topics.map(\.service)) == ["gmail", "github", "jira", "slack", "tasks"])
    let dates = topics.compactMap { Format.parse($0.updatedAt) }
    #expect(dates == dates.sorted(by: >), "newest first")
    let slack = try #require(topics.first { $0.service == "slack" })
    #expect(try await desk.history(topicID: slack.id).count == slack.items.count)
    #expect(try await desk.services().map(\.service) == ["github", "gmail", "jira", "slack", "tasks"])
}
