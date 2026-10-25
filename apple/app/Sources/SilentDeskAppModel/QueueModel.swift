/// The main window: the topic queue, search, Refresh and automatic syncing,
/// as the GTK app's window.py does it. See legacy/docs/specs/sync.md.

import Foundation
import Observation
import SilentDeskCore

@MainActor
@Observable
public final class QueueModel {
    /// Every connected service syncs this often while the app is open, in seconds.
    public static let syncEvery: Double = 120
    /// Coming back to the app syncs if the last round started this long ago.
    public static let syncOnActiveAfter: Double = 30

    /// What the queue shows.
    public enum Content: Sendable, Equatable {
        case list
        case empty
        case noMatch
    }

    public let desk: any Desk
    public let notices: Notices
    private let clock: @MainActor () -> Double

    /// Every topic, newest first.
    public private(set) var topics: [TopicView] = []
    public private(set) var lastSynced: String?
    public private(set) var refreshing = false
    /// When the last round started, on `clock`.
    public private(set) var roundStarted: Double?
    public var query = ""
    /// The open topic's ID. Cleared when the topic is gone.
    public var selection: String?

    /// `clock` counts seconds and never goes back, such as the system uptime.
    public init(
        desk: any Desk, notices: Notices = Notices(),
        clock: @escaping @MainActor () -> Double = { ProcessInfo.processInfo.systemUptime }
    ) {
        self.desk = desk
        self.notices = notices
        self.clock = clock
    }

    /// The topics the search lets through.
    public var shown: [TopicView] {
        let query = query.trimmingCharacters(in: .whitespaces)
        return query.isEmpty ? topics : topics.filter { Format.matches($0, query) }
    }

    public var content: Content {
        if !shown.isEmpty { return .list }
        return topics.isEmpty ? .empty : .noMatch
    }

    public var selectedTopic: TopicView? {
        selection.flatMap { id in topics.first { $0.id == id } }
    }

    /// "Updated … ago", or "Refreshing…" while a round runs.
    public func status(now: Date) -> String {
        if refreshing { return "Refreshing…" }
        guard let lastSynced else { return "" }
        return "Updated \(Format.ago(lastSynced, now: now))"
    }

    /// Reads the topics and when they last changed, then shows them.
    public func load() async {
        do {
            let topics = try await desk.topics()
            let lastSynced = try await desk.lastSynced()
            self.topics = topics
            self.lastSynced = lastSynced
            if let selection, !topics.contains(where: { $0.id == selection }) {
                self.selection = nil
            }
        } catch {
            notices.fail(error)
        }
    }

    /// A sync round of every connected service, unless one is running.
    public func refresh() async {
        guard !refreshing else { return }
        refreshing = true
        roundStarted = clock()
        do {
            try await desk.sync(nil)
        } catch {
            notices.fail(error)
        }
        refreshing = false
        await load()
    }

    /// The app came to the front: a round, if the last one is old enough.
    public func becameActive() async {
        if let roundStarted, clock() - roundStarted <= Self.syncOnActiveAfter {
            return
        }
        await refresh()
    }

    /// Rounds every `syncEvery` seconds until the task is cancelled.
    public func syncPeriodically() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(Self.syncEvery))
            if Task.isCancelled { return }
            await refresh()
        }
    }

    /// Syncs one service outside the rounds, such as right after it
    /// connects, then shows the topics.
    public func sync(_ service: String) async {
        do {
            try await desk.sync(service)
        } catch {
            notices.fail(error)
        }
        await load()
    }

    /// A service connected, so it syncs, or disconnected, so its topics go.
    public func serviceChanged(_ service: String, connected: Bool) async {
        if connected {
            await sync(service)
        } else {
            await load()
        }
    }

    public func replied(_ topic: TopicView) async {
        await sync(topic.service)
    }

    public func deleted(_ topic: TopicView) async {
        if selection == topic.id {
            selection = nil
        }
        notices.post(Services.deletion(topic.service, .topic).done)
        await load()
    }

    public func itemDeleted(_ topic: TopicView) async {
        notices.post(Services.deletion(topic.service, .item).done)
        await load()
    }
}
