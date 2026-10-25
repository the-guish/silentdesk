import Foundation
import SilentDeskCore

/// A desk whose answers the test sets, and which records every call.
actor FakeDesk: Desk {
    var topicList: [TopicView] = []
    var statuses: [ServiceStatus] = []
    var synced: String?
    var conversation: [Message]?
    /// Thrown by the next call of that name, then cleared.
    var failures: [String: any Error] = [:]
    private(set) var calls: [String] = []
    /// While set, `sync` waits until `release()`.
    private var held: [CheckedContinuation<Void, Never>] = []
    private var holding = false

    func set(topics: [TopicView]) { topicList = topics }
    func set(statuses: [ServiceStatus]) { self.statuses = statuses }
    func set(synced: String?) { self.synced = synced }
    func set(conversation: [Message]?) { self.conversation = conversation }
    func fail(_ call: String, with error: any Error) { failures[call] = error }

    func hold() { holding = true }

    func release() {
        holding = false
        held.forEach { $0.resume() }
        held = []
    }

    var waiting: Int { held.count }

    private func record(_ call: String) throws {
        calls.append(call)
        let name = String(call.prefix { $0 != " " })
        if let error = failures.removeValue(forKey: name) {
            throw error
        }
    }

    func topics() async throws -> [TopicView] {
        try record("topics")
        return topicList
    }

    func services() async throws -> [ServiceStatus] {
        try record("services")
        return statuses
    }

    func connect(_ service: String, params: [String: String]) async throws -> ServiceStatus {
        try record("connect \(service) \(params.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: ","))")
        return ServiceStatus(service: service, configured: true, connected: true, account: nil)
    }

    func disconnect(_ service: String) async throws -> ServiceStatus {
        try record("disconnect \(service)")
        return ServiceStatus(service: service, configured: true, connected: false, account: nil)
    }

    func sync(_ service: String?) async throws {
        if holding {
            await withCheckedContinuation { held.append($0) }
        }
        try record("sync \(service ?? "all")")
    }

    func lastSynced() async throws -> String? {
        try record("lastSynced")
        return synced
    }

    func history(topicID: String) async throws -> [Message] {
        try record("history \(topicID)")
        guard let conversation else {
            throw ConnectorError.unsupported("github", "No conversation.")
        }
        return conversation
    }

    func reply(topicID: String, body: String) async throws {
        try record("reply \(topicID) \(body)")
    }

    func delete(topicID: String) async throws {
        try record("delete \(topicID)")
    }

    func deleteItem(topicID: String, itemKey: String) async throws {
        try record("deleteItem \(topicID) \(itemKey)")
    }
}

func item(
    _ key: String, _ direction: Direction? = .inbound, author: String? = nil, date: String = "2026-10-20T10:00:00Z",
    url: String? = nil, deletable: Bool = false
) -> Item {
    Item(key: key, direction: direction, author: author, url: url, date: date, deletable: deletable)
}

func topic(
    _ id: String, service: String = "gmail", title: String? = nil, items: [Item]? = nil, deletable: Bool = false
) -> TopicView {
    let items = items ?? [item("\(id)-1")]
    return TopicView(
        id: id, service: service, title: title ?? id, items: items, updatedAt: items.last!.date, deletable: deletable)
}

/// A clock the test moves by hand.
@MainActor
final class ManualClock {
    var now: Double = 1000
}

/// Waits until `condition` holds, yielding so other tasks run.
@MainActor
func eventually(_ condition: () async -> Bool) async {
    for _ in 0..<1000 {
        if await condition() { return }
        await Task.yield()
    }
}
