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
        let days = floorDivide(seconds, 86400)
        let secondOfDay = seconds - days * 86400
        let (year, month, day) = civil(fromDays: days)
        var text = pad(year, 4) + "-" + pad(Int64(month), 2) + "-" + pad(Int64(day), 2)
        text += "T" + pad(secondOfDay / 3600, 2) + ":" + pad(secondOfDay % 3600 / 60, 2) + ":" + pad(secondOfDay % 60, 2)
        if milliseconds > 0 {
            var fraction = pad(Int64(milliseconds), 3)
            while fraction.hasSuffix("0") { fraction.removeLast() }
            text += "." + fraction
        }
        return text + "Z"
    }

    /// Milliseconds since the epoch, as Gmail counts them.
    static func format(milliseconds: Int64) -> String {
        let seconds = floorDivide(milliseconds, 1000)
        return format(seconds: seconds, milliseconds: Int(milliseconds - seconds * 1000))
    }

    /// An ISO 8601 moment with a UTC offset, such as Jira's
    /// 2026-10-23T10:00:00.000+0200, as RFC 3339 in UTC to the second. Nil
    /// for anything else, including a moment without an offset.
    static func fromISO8601(_ text: String) -> String? {
        var scanner = Scanner(text: text)
        guard let year = scanner.digits(4), scanner.take("-"), let month = scanner.digits(2), scanner.take("-"),
            let day = scanner.digits(2), scanner.take("T") || scanner.take(" "),
            let hour = scanner.digits(2), scanner.take(":"), let minute = scanner.digits(2)
        else { return nil }
        var second = 0
        if scanner.take(":") {
            guard let value = scanner.digits(2) else { return nil }
            second = value
            if scanner.take(".") {
                guard scanner.digits(atLeast: 1) != nil else { return nil }
            }
        }
        var offset = 0
        if scanner.take("Z") || scanner.take("z") {
            offset = 0
        } else if let sign = scanner.sign() {
            guard let hours = scanner.digits(2) else { return nil }
            _ = scanner.take(":")
            guard let minutes = scanner.digits(2) else { return nil }
            offset = sign * (hours * 3600 + minutes * 60)
        } else {
            return nil
        }
        guard scanner.atEnd, (1...12).contains(month), (1...31).contains(day), hour < 24, minute < 60, second < 61
        else { return nil }
        let seconds = days(fromCivil: Int64(year), month, day) * 86400 + Int64(hour * 3600 + minute * 60 + second)
        return format(seconds: seconds - Int64(offset))
    }

    private struct Scanner {
        let characters: [Character]
        var position = 0

        init(text: String) {
            characters = Array(text)
        }

        var atEnd: Bool { position == characters.count }

        mutating func take(_ character: Character) -> Bool {
            guard position < characters.count, characters[position] == character else { return false }
            position += 1
            return true
        }

        mutating func sign() -> Int? {
            if take("+") { return 1 }
            if take("-") { return -1 }
            return nil
        }

        mutating func digits(_ count: Int) -> Int? {
            guard position + count <= characters.count else { return nil }
            let slice = characters[position..<position + count]
            guard slice.allSatisfy({ $0.isASCII && $0.isNumber }), let value = Int(String(slice)) else { return nil }
            position += count
            return value
        }

        mutating func digits(atLeast minimum: Int) -> Int? {
            let start = position
            while position < characters.count, characters[position].isASCII, characters[position].isNumber {
                position += 1
            }
            return position - start >= minimum ? position - start : nil
        }
    }

    // Days since 1970-01-01 to and from a civil date, after Howard Hinnant's
    // algorithms, which hold for every year of the proleptic Gregorian calendar.

    static func civil(fromDays days: Int64) -> (year: Int64, month: Int, day: Int) {
        let z = days + 719468
        let era = (z >= 0 ? z : z - 146096) / 146097
        let dayOfEra = z - era * 146097
        let yearOfEra = (dayOfEra - dayOfEra / 1460 + dayOfEra / 36524 - dayOfEra / 146096) / 365
        let year = yearOfEra + era * 400
        let dayOfYear = dayOfEra - (365 * yearOfEra + yearOfEra / 4 - yearOfEra / 100)
        let shiftedMonth = (5 * dayOfYear + 2) / 153
        let day = dayOfYear - (153 * shiftedMonth + 2) / 5 + 1
        let month = shiftedMonth < 10 ? shiftedMonth + 3 : shiftedMonth - 9
        return (month <= 2 ? year + 1 : year, Int(month), Int(day))
    }

    static func days(fromCivil year: Int64, _ month: Int, _ day: Int) -> Int64 {
        let year = month <= 2 ? year - 1 : year
        let era = (year >= 0 ? year : year - 399) / 400
        let yearOfEra = year - era * 400
        let shiftedMonth = Int64(month > 2 ? month - 3 : month + 9)
        let dayOfYear = (153 * shiftedMonth + 2) / 5 + Int64(day) - 1
        let dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
        return era * 146097 + dayOfEra - 719468
    }

    private static func floorDivide(_ value: Int64, _ divisor: Int64) -> Int64 {
        let quotient = value / divisor
        return value % divisor < 0 ? quotient - 1 : quotient
    }

    private static func pad(_ value: Int64, _ width: Int) -> String {
        let text = String(value)
        return text.count >= width ? text : String(repeating: "0", count: width - text.count) + text
    }
}
