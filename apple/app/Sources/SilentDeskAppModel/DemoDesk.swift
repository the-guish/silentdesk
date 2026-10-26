/// A desk with made-up topics and services, kept in memory, for the
/// screenshots CI takes of the app. It never reaches a service.

import Foundation
import SilentDeskCore

public actor DemoDesk: Desk {
    private var topicList: [TopicView]
    private var statuses: [ServiceStatus]
    private let conversations: [String: [Message]]
    private let synced: String

    public init(now: Date = Date()) {
        func at(_ minutesAgo: Double) -> String {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            return formatter.string(from: now.addingTimeInterval(-minutesAgo * 60))
        }
        func item(
            _ key: String, _ direction: Direction?, _ author: String?, _ minutesAgo: Double, url: String? = nil,
            deletable: Bool = false
        ) -> Item {
            Item(key: key, direction: direction, author: author, url: url, date: at(minutesAgo), deletable: deletable)
        }
        let day = 24.0 * 60
        topicList = [
            TopicView(
                id: "demo-gmail-planning", service: "gmail", title: "Q4 planning: headcount and budget",
                items: [
                    item("m1", .inbound, "Ana López", 3 * 60, deletable: true),
                    item("m2", .outbound, "Sam Rivera", 2 * 60, deletable: true),
                    item("m3", .inbound, "Ben Carter", 12, deletable: true),
                ],
                updatedAt: at(12), deletable: true),
            TopicView(
                id: "demo-slack-release", service: "slack", title: "#release-train",
                items: [
                    item("s1", .inbound, "Priya Shah", 50),
                    item("s2", .inbound, "Marco Rossi", 35),
                ],
                updatedAt: at(35), deletable: false),
            TopicView(
                id: "demo-github-pr", service: "github", title: "Add the Keychain keyring to the Swift core",
                items: [item("pr-51", .inbound, "octocat", 4 * 60, url: "https://github.com")],
                updatedAt: at(4 * 60), deletable: false),
            TopicView(
                id: "demo-jira-ops", service: "jira", title: "OPS-142 Rotate the staging certificates",
                items: [item("OPS-142", .inbound, "Priya Shah", day + 30, url: "https://example.atlassian.net")],
                updatedAt: at(day + 30), deletable: false,
                status: TopicStatus(name: "Waiting for Customer", category: .inProgress)),
            TopicView(
                id: "demo-jira-login", service: "jira", title: "PAY-412 Fix the login timeout on slow networks",
                items: [item("PAY-412", .outbound, "Ben Carter", 2 * day, url: "https://example.atlassian.net")],
                updatedAt: at(2 * day), deletable: false,
                status: TopicStatus(name: "To Do", category: .new)),
            TopicView(
                id: "demo-gmail-invoice", service: "gmail", title: "Invoice 2026-10 from Acme Cloud",
                items: [
                    item("i1", .inbound, "Acme Billing", 3 * day),
                    item("i2", .outbound, "Sam Rivera", 3 * day - 20),
                ],
                updatedAt: at(3 * day - 20), deletable: false),
            TopicView(
                id: "demo-tasks-agenda", service: "tasks", title: "Send the offsite agenda",
                items: [item("t1", nil, nil, 40 * day)],
                updatedAt: at(40 * day), deletable: true),
        ]
        conversations = [
            "demo-slack-release": [
                Message(
                    key: "s1", direction: .inbound, author: "Priya Shah", text: "The release branch is cut. Freeze starts now.",
                    date: at(50)),
                Message(
                    key: "s2", direction: .inbound, author: "Marco Rossi",
                    text: "Could someone review the migration fix before 3pm?", date: at(35)),
            ],
        ]
        statuses = [
            ServiceStatus(service: "github", configured: true, connected: true, account: "sam-rivera"),
            ServiceStatus(service: "gmail", configured: true, connected: true, account: "sam@example.com"),
            ServiceStatus(service: "jira", configured: true, connected: false, account: nil),
            ServiceStatus(service: "slack", configured: true, connected: true, account: "Example Inc."),
            ServiceStatus(service: "tasks", configured: false, connected: false, account: nil),
        ]
        synced = at(3)
    }

    public func topics() async throws -> [TopicView] { topicList }

    public func services() async throws -> [ServiceStatus] { statuses }

    public func connect(_ service: String, params: [String: String]) async throws -> ServiceStatus {
        try setConnected(service, true, account: params["email"] ?? "demo")
    }

    public func disconnect(_ service: String) async throws -> ServiceStatus {
        topicList.removeAll { $0.service == service }
        return try setConnected(service, false, account: nil)
    }

    public func sync(_ service: String?) async throws {}

    public func lastSynced() async throws -> String? { synced }

    public func history(topicID: String) async throws -> [Message] {
        guard let messages = conversations[topicID] else {
            throw ConnectorError.unsupported(nil, "This service keeps no conversation.")
        }
        return messages
    }

    public func reply(topicID: String, body: String) async throws {}

    public func delete(topicID: String) async throws {
        topicList.removeAll { $0.id == topicID }
    }

    public func deleteItem(topicID: String, itemKey: String) async throws {
        guard let index = topicList.firstIndex(where: { $0.id == topicID }) else { return }
        let topic = topicList[index]
        let items = topic.items.filter { $0.key != itemKey }
        if items.isEmpty {
            topicList.remove(at: index)
        } else {
            topicList[index] = TopicView(
                id: topic.id, service: topic.service, title: topic.title, items: items,
                updatedAt: items.last!.date, deletable: topic.deletable)
        }
    }

    private func setConnected(_ service: String, _ connected: Bool, account: String?) throws -> ServiceStatus {
        guard let index = statuses.firstIndex(where: { $0.service == service }) else {
            throw ConnectorError.unsupported(service, "Unknown service.")
        }
        statuses[index] = ServiceStatus(service: service, configured: true, connected: connected, account: account)
        return statuses[index]
    }
}
