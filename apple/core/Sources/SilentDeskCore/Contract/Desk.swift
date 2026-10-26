/// What the desk app offers the user interfaces: the CLI and the apps.

/// One topic, as the queue and the topic screen show it.
public struct TopicView: Sendable, Equatable {
    /// SilentDesk's own ID, a UUID.
    public let id: String
    public let service: String
    public let title: String
    /// One or more, oldest first.
    public let items: [Item]
    /// RFC 3339: the newest item's date.
    public let updatedAt: String
    /// The whole topic can be deleted: its connector can delete it at once,
    /// or every item can be deleted.
    public let deletable: Bool
    /// The topic's project, or nil for Default.
    public let projectId: String?

    public init(
        id: String, service: String, title: String, items: [Item], updatedAt: String, deletable: Bool,
        projectId: String? = nil
    ) {
        self.id = id
        self.service = service
        self.title = title
        self.items = items
        self.updatedAt = updatedAt
        self.deletable = deletable
        self.projectId = projectId
    }
}

public protocol Desk: Sendable {
    /// Every topic, newest first.
    func topics() async throws -> [TopicView]

    /// Every service SilentDesk can connect, connected or not, sorted by name.
    func services() async throws -> [ServiceStatus]

    /// Connects one service.
    func connect(_ service: String, params: [String: String]) async throws -> ServiceStatus

    /// Disconnects one service and drops its topics.
    func disconnect(_ service: String) async throws -> ServiceStatus

    /// Syncs one service, or every connected service in turn when `service` is nil.
    func sync(_ service: String?) async throws

    /// When topics last changed, in RFC 3339, or nil before the first sync.
    func lastSynced() async throws -> String?

    /// A topic's recent messages with their text, read live from its service.
    func history(topicID: String) async throws -> [Message]

    /// Replies in a topic, through its service's connector.
    func reply(topicID: String, body: String) async throws

    /// Deletes a deletable topic in its service, through its connector, and
    /// drops it: at once if the connector can, otherwise item by item,
    /// stopping at the first failure with what was deleted kept deleted.
    /// Throws `unsupported` for a topic that is not deletable.
    func delete(topicID: String) async throws

    /// Deletes one deletable item of a topic in its service, and keeps the
    /// topic as its connector then reports it, or drops it when gone. Throws
    /// `UnknownItem` for a key the topic does not have, and `unsupported` for
    /// an item that is not deletable.
    func deleteItem(topicID: String, itemKey: String) async throws
}
