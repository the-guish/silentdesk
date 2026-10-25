/// Timestamps in RFC 3339, UTC, as the contract requires: 2026-10-24T12:00:00Z.

import Foundation

enum RFC3339 {
    /// The time now, to the second.
    static func now() -> String {
        format(seconds: Int64(Date().timeIntervalSince1970.rounded(.down)))
    }

    /// A moment as seconds since the epoch, with an optional fraction in
    /// milliseconds, which is written with its trailing zeros removed.
    static func format(seconds: Int64, milliseconds: Int = 0) -> String {
        var text = formatter("yyyy-MM-dd'T'HH:mm:ss").string(from: Date(timeIntervalSince1970: TimeInterval(seconds)))
        if milliseconds > 0 {
            var fraction = String(milliseconds)
            fraction = String(repeating: "0", count: max(0, 3 - fraction.count)) + fraction
            while fraction.hasSuffix("0") { fraction.removeLast() }
            text += "." + fraction
        }
        return text + "Z"
    }

    /// Milliseconds since the epoch, as Gmail counts them.
    static func format(milliseconds: Int64) -> String {
        let seconds = milliseconds >= 0 ? milliseconds / 1000 : (milliseconds - 999) / 1000
        return format(seconds: seconds, milliseconds: Int(milliseconds - seconds * 1000))
    }

    /// An ISO 8601 moment with a UTC offset, such as Jira's
    /// 2026-10-23T10:00:00.000+0200, as RFC 3339 in UTC to the second. Nil
    /// for anything else, including a moment without an offset.
    static func fromISO8601(_ text: String) -> String? {
        for pattern in iso8601Patterns {
            if let date = formatter(pattern).date(from: text) {
                return format(seconds: Int64(date.timeIntervalSince1970.rounded(.down)))
            }
        }
        return nil
    }

    /// With or without a fraction, the offset as +0200, +02:00 or Z.
    private static let iso8601Patterns = [
        "yyyy-MM-dd'T'HH:mm:ss.SSSXXX", "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss.SSSZZZZZ", "yyyy-MM-dd'T'HH:mm:ssZZZZZ",
        "yyyy-MM-dd'T'HH:mm:ss.SSSZ", "yyyy-MM-dd'T'HH:mm:ssZ",
        "yyyy-MM-dd'T'HH:mmXXX", "yyyy-MM-dd'T'HH:mmZ",
    ]

    /// A formatter free of the user's locale, calendar and time zone.
    private static func formatter(_ pattern: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = pattern
        return formatter
    }
}
