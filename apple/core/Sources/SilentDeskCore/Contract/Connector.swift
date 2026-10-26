/// What every connector app offers for each service it connects: Gmail,
/// Google Tasks, Slack, Jira and GitHub. A connector both reads from its
/// service and sends to it.

public enum Direction: String, Sendable, Equatable {
    case inbound
    case outbound
}

/// Where a status stands, the same for every service.
public enum StatusCategory: String, Sendable, Equatable {
    case new
    case inProgress
    case done
}

/// The status a service gives a topic, such as a Jira issue's. See
/// docs/specs/topic-status.md.
public struct TopicStatus: Sendable, Equatable {
    /// As the service writes it, such as "Code Review".
    public let name: String
    public let category: StatusCategory?

    public init(name: String, category: StatusCategory?) {
        self.name = name
        self.category = category
    }
}

/// What the user needs to know about one service.
public struct ServiceStatus: Sendable, Equatable {
    public let service: String
    /// The app has the client ID or settings it needs to sign in.
    public let configured: Bool
    public let connected: Bool
    /// The account as shown to the user, such as an email address.
    public let account: String?

    public init(service: String, configured: Bool, connected: Bool, account: String?) {
        self.service = service
        self.configured = configured
        self.connected = connected
        self.account = account
    }
}

/// One message in a topic, such as an email or a chat message. A task, an
/// issue or a pull request is a topic with one item. Only what the queue
/// shows: bodies are never kept.
public struct Item: Sendable, Equatable {
    /// Stable within the service, such as a Gmail message ID.
    public let key: String
    public let direction: Direction?
    /// Who wrote it, as shown to the user.
    public let author: String?
    /// Opens the item in its own system.
    public let url: String?
    /// RFC 3339.
    public let date: String
    /// The user can delete it in its service now, as the connector judges it
    /// at sync time. The service has the last word: its refusal is an error.
    public let deletable: Bool

    public init(key: String, direction: Direction?, author: String?, url: String?, date: String, deletable: Bool) {
        self.key = key
        self.direction = direction
        self.author = author
        self.url = url
        self.date = date
        self.deletable = deletable
    }
}

/// A unit of work, as the connector groups it: an email thread, a chat
/// conversation, a task, an issue or a pull request.
public struct Topic: Sendable, Equatable {
    /// Stable within the service, such as a Gmail thread ID.
    public let key: String
    public let title: String
    /// One or more, oldest first.
    public let items: [Item]
    /// The service can delete the whole topic now, in one operation, such as
    /// trashing a Gmail thread. When this is false but every item is
    /// deletable, the desk deletes the topic item by item instead.
    public let deletable: Bool
    /// nil for a service that gives its topics no status.
    public let status: TopicStatus?

    public init(key: String, title: String, items: [Item], deletable: Bool, status: TopicStatus? = nil) {
        self.key = key
        self.title = title
        self.items = items
        self.deletable = deletable
        self.status = status
    }
}

/// One message of a topic with its text, read live for the topic screen.
/// Shown, never stored.
public struct Message: Sendable, Equatable {
    public let key: String
    public let direction: Direction?
    public let author: String?
    public let text: String
    /// RFC 3339.
    public let date: String

    public init(key: String, direction: Direction?, author: String?, text: String, date: String) {
        self.key = key
        self.direction = direction
        self.author = author
        self.text = text
        self.date = date
    }
}

/// What one sync found. When `complete` is true, `topics` is everything the
/// service has now, and any topic not in it is gone.
public struct SyncResult: Sendable, Equatable {
    /// New or changed topics, each with all of its items.
    public let topics: [Topic]
    /// Keys of topics that are gone from the service.
    public let removed: [String]
    public let complete: Bool

    public init(topics: [Topic], removed: [String], complete: Bool) {
        self.topics = topics
        self.removed = removed
        self.complete = complete
    }
}

/// One connected service.
protocol Connector: Sendable {
    /// The service's name, such as "gmail".
    var service: String { get }

    /// Whether the service is configured and connected, and to which account.
    func status() async throws -> ServiceStatus

    /// Signs in, with the user's form fields or through the browser.
    func connect(_ params: [String: String]) async throws -> ServiceStatus

    /// Signs out and forgets everything kept for this service.
    func disconnect() async throws -> ServiceStatus

    /// Reads what changed since the last sync.
    func sync() async throws -> SyncResult

    /// Replies in the topic with this key, as the connected account. Throws
    /// an `unsupported` error if the service has no replies.
    func reply(topicKey: String, body: String) async throws

    /// The topic's recent messages with their text, oldest first, read live
    /// from the service. Throws an `unsupported` error if the service has none.
    func history(topicKey: String) async throws -> [Message]

    /// Deletes the topic with this key in its service, such as moving an
    /// email thread to the trash. The desk calls it only for a topic marked
    /// deletable; `unsupported` is a safety net for any other. Later syncs
    /// must not send the topic again unless the service has it again.
    func deleteTopic(topicKey: String) async throws

    /// Deletes one item of the topic in its service, such as moving one email
    /// to the trash, and returns the topic as it is now, or nil when it is
    /// gone: its title or deletability may change with its items. The desk
    /// calls it only for an item marked deletable; `unsupported` is a safety
    /// net for any other. Later syncs must not send the item again unless the
    /// service has it again.
    func deleteItem(topicKey: String, itemKey: String) async throws -> Topic?
}
