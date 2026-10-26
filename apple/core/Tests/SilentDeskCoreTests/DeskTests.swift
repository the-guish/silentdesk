@testable import SilentDeskCore
import Testing

private func item(_ key: String, _ date: String, deletable: Bool = false) -> Item {
    Item(key: key, direction: .inbound, author: nil, url: nil, date: date, deletable: deletable)
}

private func record(_ key: String, id: String = "id-\(Int.random(in: 1...1_000_000))", date: String = "2026-10-01T00:00:00Z", deletable: Bool = false) -> TopicRecord {
    TopicRecord(
        id: id, service: "s", key: key, title: key, items: [item("\(key)-1", date, deletable: deletable)],
        createdAt: "2026-09-01T00:00:00Z", updatedAt: date, deletable: deletable)
}

@Test func aCompleteSyncReplacesEverythingButKeepsIDs() {
    var old = record("a", id: "A", date: "2026-10-01T00:00:00Z")
    old.projectId = "P"
    let gone = record("b", id: "B")
    let result = SyncResult(
        topics: [
            Topic(key: "a", title: "A again", items: [item("a-1", "2026-10-02T00:00:00Z")], deletable: false),
            Topic(key: "c", title: "New", items: [item("c-1", "2026-10-03T00:00:00Z")], deletable: false),
        ], removed: [], complete: true)
    var next = 0
    let applied = Topics.apply([old, gone], service: "s", result: result, now: "2026-10-05T00:00:00Z") {
        next += 1
        return "new-\(next)"
    }
    #expect(applied.map(\.key) == ["a", "c"])
    #expect(applied[0].id == "A", "a changed topic keeps its ID")
    #expect(applied[0].createdAt == "2026-09-01T00:00:00Z")
    #expect(applied[0].updatedAt == "2026-10-02T00:00:00Z")
    #expect(applied[0].title == "A again")
    #expect(applied[0].projectId == "P", "a changed topic keeps its project")
    #expect(applied[1].projectId == nil, "a new topic starts in Default")
    #expect(applied[1].id == "new-1")
    #expect(applied[1].createdAt == "2026-10-05T00:00:00Z")
}

@Test func anIncrementalSyncKeepsWhatItDoesNotMention() {
    let kept = record("a", id: "A")
    let removed = record("b", id: "B")
    let result = SyncResult(
        topics: [Topic(key: "c", title: "C", items: [item("c-1", "2026-10-03T00:00:00Z")], deletable: true)],
        removed: ["b"], complete: false)
    let applied = Topics.apply([kept, removed], service: "s", result: result, now: "now") { "new" }
    #expect(applied.map(\.key) == ["a", "c"])
    #expect(applied[0] == kept)
    #expect(applied[1].deletable)
}

@Test func topicsAreNewestFirstThenByID() {
    let records = [
        record("a", id: "1", date: "2026-10-01T00:00:00Z"),
        record("b", id: "2", date: "2026-10-03T00:00:00Z"),
        record("c", id: "3", date: "2026-10-03T00:00:00Z"),
    ]
    #expect(Topics.newestFirst(records).map(\.id) == ["3", "2", "1"])
}

@Test func deletabilityFollowsTheConnectorOrEveryItem() {
    #expect(Topics.deletable(record("a", deletable: true)))
    let byItems = TopicRecord(
        id: "x", service: "s", key: "k", title: "t", items: [item("1", "d", deletable: true), item("2", "d", deletable: true)],
        createdAt: "c", updatedAt: "u", deletable: false)
    #expect(Topics.deletable(byItems))
    #expect(Topics.byItems(byItems))
    let mixed = TopicRecord(
        id: "x", service: "s", key: "k", title: "t", items: [item("1", "d", deletable: true), item("2", "d")],
        createdAt: "c", updatedAt: "u", deletable: false)
    #expect(!Topics.deletable(mixed))
    #expect(!Topics.byItems(record("a", deletable: true)), "a topic its connector deletes at once is not deleted by items")
}

@Test func aRoundSyncsInTheContractOrder() {
    #expect(SyncRounds.roundOrder(["gmail", "zulip", "github", "tasks"]) == ["tasks", "github", "gmail", "zulip"])
    #expect(SyncRounds.roundOrder([]) == [])
}

@Test func aTopicOfAServiceNoLongerWiredIsAnUnknownService() async throws {
    let folder = try temporaryFolder()
    let database = SqlcipherDatabase(path: "\(folder)/silentdesk.db", keyring: FileKeyring(path: "\(folder)/keyring.json"))
    let store = SqlcipherTopicStore(database: database)
    let left = TopicRecord(
        id: "T", service: "gone", key: "k", title: "t", items: [item("i", "2026-10-01T00:00:00Z", deletable: true)],
        createdAt: "2026-09-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", deletable: true)
    try await store.replace("gone", with: [left])
    let desk = DeskService(connectors: [], store: store, clock: FixedClock("2026-10-05T00:00:00Z"))
    await #expect(throws: UnknownService.self) { try await desk.history(topicID: "T") }
    await #expect(throws: UnknownService.self) { try await desk.reply(topicID: "T", body: "hi") }
    await #expect(throws: UnknownService.self) { try await desk.delete(topicID: "T") }
    await #expect(throws: UnknownService.self) { try await desk.deleteItem(topicID: "T", itemKey: "i") }
}

@Test func theStoreKeepsATopicsProjectWhileTheProjectExists() async throws {
    let folder = try temporaryFolder()
    let database = SqlcipherDatabase(path: "\(folder)/silentdesk.db", keyring: FileKeyring(path: "\(folder)/keyring.json"))
    try database.transaction { db in
        try db.execute("INSERT INTO desk_projects (id, name) VALUES (?, ?)", [.text("P"), .text("Work")])
    }
    let store = SqlcipherTopicStore(database: database)
    var kept = record("a", id: "A")
    kept.projectId = "P"
    var orphan = record("b", id: "B")
    orphan.projectId = "gone"
    try await store.replace("s", with: [kept, orphan])
    let projects = Dictionary(uniqueKeysWithValues: try await store.topics().map { ($0.id, $0.projectId) })
    #expect(projects["A"] == .some("P"))
    #expect(projects["B"] == .some(nil), "a project deleted while the service synced leaves its topic in Default")
}
