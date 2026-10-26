/// Short messages a window shows for a few seconds, such as "Reply sent" or
/// why a sync failed: the GTK app's toasts.

import Foundation
import Observation

public struct Notice: Sendable, Equatable, Identifiable {
    public let id: UUID
    public let text: String
    /// How long it stays, in seconds. Failures stay longer.
    public let seconds: Double
}

@MainActor
@Observable
public final class Notices {
    /// Oldest first; the window shows the newest.
    public private(set) var shown: [Notice] = []

    public init() {}

    public var current: Notice? { shown.last }

    public func post(_ text: String, seconds: Double = 4) {
        shown.append(Notice(id: UUID(), text: text, seconds: seconds))
    }

    public func fail(_ error: any Error) {
        post(Format.describe(error), seconds: 6)
    }

    public func dismiss(_ id: UUID) {
        shown.removeAll { $0.id == id }
    }
}
