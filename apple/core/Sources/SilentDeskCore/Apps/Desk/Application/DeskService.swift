/// The desk's use cases, exposed through `Desk`.

import Foundation

/// The reply on stdin was empty.
public struct EmptyReply: Error, Sendable, CustomStringConvertible {
    public let message: String
    public var description: String { message }
}

final class DeskService: Desk {
    private let connectors: [String: any Connector]
    private let store: any TopicStore
    private let clock: any Clock
    private let newID: @Sendable () -> String
    /// One operation per service at a time: a second one waits.
    private let locks: [String: AsyncMutex]

    init(
        connectors: [any Connector],
        store: any TopicStore,
        clock: any Clock,
        newID: @escaping @Sendable () -> String = { UUID().uuidString.lowercased() }
    ) {
        self.connectors = Dictionary(connectors.map { ($0.service, $0) }, uniquingKeysWith: { first, _ in first })
        self.store = store
        self.clock = clock
        self.newID = newID
        locks = self.connectors.mapValues { _ in AsyncMutex() }
    }

    private var serviceNames: [String] {
        connectors.keys.sorted()
    }

    func topics() async throws -> [TopicView] {
        Topics.newestFirst(try await store.topics()).map { record in
            TopicView(
                id: record.id, service: record.service, title: record.title, items: record.items,
                updatedAt: record.updatedAt, deletable: Topics.deletable(record))
        }
    }

    func services() async throws -> [ServiceStatus] {
        var statuses: [ServiceStatus] = []
        for name in serviceNames {
            statuses.append(try await connectors[name]!.status())
        }
        return statuses
    }

    private func unknown(_ service: String) -> UnknownService {
        UnknownService(message: "Unknown service '\(service)'. Services: \(serviceNames.joined(separator: ", ")).")
    }

    private func connector(_ service: String) throws -> any Connector {
        guard let connector = connectors[service] else {
            throw unknown(service)
        }
        return connector
    }

    /// A stored topic can name a service this build does not wire.
    private func locked<T: Sendable>(_ service: String, _ body: @Sendable () async throws -> T) async throws -> T {
        guard let lock = locks[service] else {
            throw unknown(service)
        }
        return try await lock.withLock(body)
    }

    func connect(_ service: String, params: [String: String]) async throws -> ServiceStatus {
        let connector = try connector(service)
        return try await locked(service) {
            let before = try await connector.status()
            let status = try await connector.connect(params)
            if status.account != before.account {
                // Another account: the old one's topics are not this one's.
                try await self.store.replace(service, with: [])
            }
            return status
        }
    }

    func disconnect(_ service: String) async throws -> ServiceStatus {
        let connector = try connector(service)
        return try await locked(service) {
            let status = try await connector.disconnect()
            try await self.store.replace(service, with: [])
            return status
        }
    }

    func sync(_ service: String?) async throws {
        if let service {
            _ = try connector(service)
            try await syncOne(service)
            return
        }
        // A round: every connected service in turn. One failure does not stop
        // the others; they are all reported together at the end.
        var connected: [String] = []
        for name in serviceNames where try await connectors[name]!.status().connected {
            connected.append(name)
        }
        var failures: [SyncFailed.Failure] = []
        for name in SyncRounds.roundOrder(connected) {
            do {
                try await syncOne(name)
            } catch {
                failures.append(SyncFailed.Failure(service: name, error: error))
            }
        }
        if !failures.isEmpty {
            throw SyncFailed(failures: failures)
        }
    }

    private func syncOne(_ service: String) async throws {
        try await locked(service) {
            let result = try await self.connectors[service]!.sync()
            let now = self.clock.now()
            let current = try await self.store.topics().filter { $0.service == service }
            try await self.store.replace(
                service, with: Topics.apply(current, service: service, result: result, now: now, newID: self.newID))
            try await self.store.setLastSynced(now)
        }
    }

    func lastSynced() async throws -> String? {
        try await store.lastSynced()
    }

    private func record(_ topicID: String) async throws -> TopicRecord {
        guard let record = try await store.topics().first(where: { $0.id == topicID }) else {
            throw UnknownTopic(message: "No topic has the ID '\(topicID)'.")
        }
        return record
    }

    func history(topicID: String) async throws -> [Message] {
        let record = try await record(topicID)
        return try await locked(record.service) {
            try await self.connector(record.service).history(topicKey: record.key)
        }
    }

    func reply(topicID: String, body: String) async throws {
        guard !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw EmptyReply(message: "The reply is empty.")
        }
        let record = try await record(topicID)
        try await locked(record.service) {
            try await self.connector(record.service).reply(topicKey: record.key, body: body)
        }
    }

    // Deleting checks the topic inside its service's lock, so a sync that
    // finished while this waited cannot leave it checking a stale copy.

    func delete(topicID: String) async throws {
        let service = try await record(topicID).service
        try await locked(service) {
            let record = try await self.record(topicID)
            if record.deletable {
                try await self.connector(service).deleteTopic(topicKey: record.key)
                try await self.put(record, nil)
            } else if Topics.byItems(record) {
                // Oldest first. Each deleted item stays deleted if a later one
                // fails. The connector reports the topic after each one, so an
                // item it no longer has, or no longer lets go, is skipped.
                var current: TopicRecord? = record
                for key in record.items.map(\.key) {
                    if let item = current?.items.first(where: { $0.key == key }), item.deletable, let topic = current {
                        current = try await self.deleteItem(of: topic, key)
                    }
                }
            } else {
                throw ConnectorError.unsupported(service, "This topic cannot be deleted.")
            }
        }
    }

    func deleteItem(topicID: String, itemKey: String) async throws {
        let service = try await record(topicID).service
        try await locked(service) {
            let record = try await self.record(topicID)
            guard let item = record.items.first(where: { $0.key == itemKey }) else {
                throw UnknownItem(message: "The topic has no item '\(itemKey)'.")
            }
            guard item.deletable else {
                throw ConnectorError.unsupported(service, "This item cannot be deleted.")
            }
            _ = try await self.deleteItem(of: record, itemKey)
        }
    }

    /// Deletes one item through the connector, then keeps the topic as the
    /// connector reports it. Runs under the service's lock.
    private func deleteItem(of record: TopicRecord, _ itemKey: String) async throws -> TopicRecord? {
        let topic = try await connector(record.service).deleteItem(topicKey: record.key, itemKey: itemKey)
        let updated = topic.map {
            Topics.record($0, service: record.service, old: record, now: clock.now(), newID: newID)
        }
        try await put(record, updated)
        return updated
    }

    /// Replaces one stored topic with `new`, or drops it for nil.
    private func put(_ old: TopicRecord, _ new: TopicRecord?) async throws {
        let others = try await store.topics().filter { $0.service == old.service && $0.id != old.id }
        try await store.replace(old.service, with: new.map { others + [$0] } ?? others)
    }
}
