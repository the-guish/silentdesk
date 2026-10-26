/// What each service asks for to connect, and what can be done with its
/// topics. The fields are those of `silentdesk connect` in docs/specs/cli.md, as in
/// the GTK app's services.py.

import Foundation
import SilentDeskCore

public enum Services {
    public struct Field: Sendable, Equatable, Identifiable {
        public let name: String
        public let title: String
        public let secret: Bool
        public let required: Bool

        public var id: String { name }

        init(_ name: String, _ title: String, secret: Bool = false, required: Bool = true) {
            self.name = name
            self.title = title
            self.secret = secret
            self.required = required
        }
    }

    static let allFields: [String: [Field]] = [
        "github": [
            Field("token", "Personal access token", secret: true),
            Field("server", "Enterprise Server host, empty for github.com", required: false),
        ],
        "jira": [
            Field("site", "Site, such as acme.atlassian.net"),
            Field("email", "Email, for Jira Cloud only", required: false),
            Field("token", "API token", secret: true),
        ],
    ]

    /// Services that sign in through the browser, and the setting naming the
    /// app they sign in with.
    public static let browserSignIn = [
        "gmail": "SILENTDESK_GOOGLE_CLIENT_ID",
        "tasks": "SILENTDESK_GOOGLE_CLIENT_ID",
        "slack": "SILENTDESK_SLACK_CLIENT_ID",
    ]

    /// The services whose connectors can reply in a topic. Every other
    /// connector throws `unsupported`, so the topic screen offers no reply box.
    public static let canReply: Set<String> = ["gmail"]

    /// How deleting a topic or an item reads: the question that confirms it,
    /// and the notice once done. Whether it can be deleted is the
    /// connector's call, in `deletable`.
    public struct Deletion: Sendable, Equatable {
        public let heading: String
        public let body: String
        public let done: String
    }

    public enum Target: Sendable {
        case topic
        case item
    }

    static let gmailTrash = "Gmail keeps it in the trash for 30 days, then deletes it."

    public static func deletion(_ service: String, _ target: Target) -> Deletion {
        switch (service, target) {
        case ("gmail", .topic):
            return Deletion(heading: "Move this thread to the trash?", body: gmailTrash, done: "Moved to the trash")
        case ("gmail", .item):
            return Deletion(heading: "Move this message to the trash?", body: gmailTrash, done: "Moved to the trash")
        default:
            let noun = target == .topic ? "topic" : "message"
            return Deletion(
                heading: "Delete this \(noun)?", body: "SilentDesk deletes it in \(Format.serviceName(service)).",
                done: "Deleted")
        }
    }

    public static func fields(_ service: String) -> [Field] {
        allFields[service] ?? []
    }

    /// The titles of the required fields left empty.
    public static func missing(_ service: String, _ values: [String: String]) -> [String] {
        fields(service).filter { $0.required && trimmed(values[$0.name]).isEmpty }.map(\.title)
    }

    /// The fields to send, trimmed, without the empty optional ones.
    public static func connectParams(_ service: String, _ values: [String: String]) -> [String: String] {
        var params: [String: String] = [:]
        for field in fields(service) {
            let value = trimmed(values[field.name])
            if !value.isEmpty {
                params[field.name] = value
            }
        }
        return params
    }

    /// One line under the service's name.
    public static func describe(_ status: ServiceStatus) -> String {
        if status.connected {
            return status.account ?? "Connected"
        }
        if !status.configured {
            return browserSignIn[status.service].map { "Set \($0) to connect" } ?? "Not set up"
        }
        if browserSignIn[status.service] != nil {
            return "Not connected · signs in through your browser"
        }
        return "Not connected"
    }

    public static func disconnectWarning(_ service: String) -> String {
        "SilentDesk forgets your \(Format.serviceName(service)) sign-in and drops its topics."
    }

    private static func trimmed(_ text: String?) -> String {
        (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
