/// How topics read on screen: service names, dates, avatars and search text.
/// The same rules as the GTK app's format.py.

import Foundation
import SilentDeskCore

public enum Format {
    static let serviceNames = ["gmail": "Gmail", "github": "GitHub", "jira": "Jira", "slack": "Slack", "tasks": "Google Tasks"]

    public static func serviceName(_ service: String) -> String {
        serviceNames[service] ?? service.capitalized
    }

    /// An RFC 3339 date, with or without fractional seconds; nil for anything else.
    public static func parse(_ rfc3339: String?) -> Date? {
        guard let rfc3339, !rfc3339.isEmpty else { return nil }
        return withFraction.date(from: rfc3339) ?? withoutFraction.date(from: rfc3339)
    }

    /// Such as "just now", "3 min ago" or "2 h ago", for "Updated …".
    public static func ago(_ rfc3339: String?, now: Date) -> String {
        guard let moment = parse(rfc3339) else { return "just now" }
        let minutes = Int((now.timeIntervalSince(moment) / 60).rounded(.down))
        if minutes < 1 { return "just now" }
        if minutes < 60 { return "\(minutes) min ago" }
        if minutes < 48 * 60 { return "\(minutes / 60) h ago" }
        return "\(minutes / (24 * 60)) days ago"
    }

    /// A topic's date in local time: the time today, the day this year, or
    /// the full date.
    public static func shortDate(_ rfc3339: String?, now: Date, timeZone: TimeZone = .current) -> String {
        guard let moment = parse(rfc3339) else { return "" }
        let calendar = gregorian(timeZone)
        if calendar.isDate(moment, inSameDayAs: now) {
            return format(moment, "HH:mm", timeZone)
        }
        if calendar.component(.year, from: moment) == calendar.component(.year, from: now) {
            return format(moment, "MMM d", timeZone)
        }
        return format(moment, "MMM d, yyyy", timeZone)
    }

    /// An item's date in local time with the time of day: "Today 09:12",
    /// "Oct 24, 09:12", or with the year when it is not this one.
    public static func longDate(_ rfc3339: String?, now: Date, timeZone: TimeZone = .current) -> String {
        guard let moment = parse(rfc3339) else { return "" }
        let calendar = gregorian(timeZone)
        let time = format(moment, "HH:mm", timeZone)
        if calendar.isDate(moment, inSameDayAs: now) {
            return "Today \(time)"
        }
        if calendar.component(.year, from: moment) == calendar.component(.year, from: now) {
            return "\(format(moment, "MMM d", timeZone)), \(time)"
        }
        return "\(format(moment, "MMM d, yyyy", timeZone)), \(time)"
    }

    /// Under an item's author: whether the user received or sent it, and when.
    public static func itemLine(_ direction: Direction?, _ date: String, now: Date, timeZone: TimeZone = .current) -> String {
        let when = longDate(date, now: now, timeZone: timeZone)
        switch direction {
        case .outbound: return "Sent · \(when)"
        case .inbound: return "Received · \(when)"
        case nil: return when
        }
    }

    /// The service, then who the user is dealing with: who wrote the newest
    /// item, or that it waits on others when the user wrote it.
    public static func subtitle(_ topic: TopicView) -> String {
        if topic.items.last?.direction == .outbound {
            return "\(serviceName(topic.service)) · Waiting on others"
        }
        let author = topic.items.last { $0.author != nil }?.author
        return ([serviceName(topic.service)] + [author].compactMap { $0 }).joined(separator: " · ")
    }

    /// Whose initials the row's avatar shows: the newest item with an author.
    public static func avatarName(_ topic: TopicView) -> String? {
        topic.items.last { $0.author != nil }?.author
    }

    /// Up to two letters: the first and the last word's first letter. An
    /// email address counts only its part before the @.
    public static func initials(_ name: String) -> String {
        let local = name.split(separator: "@", maxSplits: 1).first ?? ""
        let words = local.split { $0.isWhitespace || $0 == "." || $0 == "_" || $0 == "-" }
        guard let first = words.first?.first else { return "" }
        guard words.count > 1, let last = words.last?.first else { return String(first).uppercased() }
        return (String(first) + String(last)).uppercased()
    }

    /// A stable pick among `count` colors for a name, the same on every run.
    public static func colorIndex(_ name: String, count: Int) -> Int {
        var hash: UInt32 = 5381
        for byte in name.utf8 {
            hash = (hash &* 33) &+ UInt32(byte)
        }
        return Int(hash % UInt32(max(count, 1)))
    }

    /// Everything a search matches against, lowercased.
    public static func searchText(_ topic: TopicView) -> String {
        var parts = [topic.title, serviceName(topic.service)]
        if let status = topic.status {
            parts.append(status.name)
        }
        for item in topic.items {
            parts += [item.author, item.key].compactMap { $0 }
        }
        return parts.joined(separator: "\n").lowercased()
    }

    /// The chip of a topic without a status (docs/specs/topic-status.md).
    public static let noStatus = "—"
    /// The chip column takes at most this share of the queue's width.
    public static let chipShare = 0.25

    /// What a topic's chip shows: its status, or a dash.
    public static func chipLabel(_ status: TopicStatus?) -> String {
        status?.name ?? noStatus
    }

    /// One width for every chip: the widest one's, at most a share of the
    /// queue's width. A queue not laid out yet, of width 0, sets no limit.
    public static func chipWidth(_ widths: [Double], queueWidth: Double) -> Double {
        let widest = widths.max() ?? 0
        return queueWidth > 0 ? min(widest, (queueWidth * chipShare).rounded(.down)) : widest
    }

    /// Where the topic opens in its service: its newest item with a link.
    public static func topicURL(_ topic: TopicView) -> String? {
        topic.items.reversed().lazy.compactMap(\.url).first
    }

    /// Whether every word of the query is in the topic.
    public static func matches(_ topic: TopicView, _ query: String) -> Bool {
        let text = searchText(topic)
        return query.lowercased().split(whereSeparator: \.isWhitespace).allSatisfy { text.contains($0) }
    }

    /// An error as one line, for a notice.
    public static func describe(_ error: any Error) -> String {
        if let failed = error as? SyncFailed {
            return failed.failures.map { "Could not sync \(serviceName($0.service)): \(describeBare($0.error))" }
                .joined(separator: " ")
        }
        if let error = error as? ConnectorError, let service = error.service {
            return "\(serviceName(service)): \(error.message)"
        }
        return describeBare(error)
    }

    private static func describeBare(_ error: any Error) -> String {
        if let localized = error as? any LocalizedError, let text = localized.errorDescription, !text.isEmpty {
            return text
        }
        // The core's errors describe themselves as their message.
        let text = String(describing: error)
        return text.isEmpty ? String(describing: type(of: error)) : text
    }

    // ISO8601DateFormatter is thread-safe once configured.
    nonisolated(unsafe) private static let withFraction: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    nonisolated(unsafe) private static let withoutFraction: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static func gregorian(_ timeZone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return calendar
    }

    private static func format(_ date: Date, _ pattern: String, _ timeZone: TimeZone) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = pattern
        return formatter.string(from: date)
    }
}
