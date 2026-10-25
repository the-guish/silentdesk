/// JSON documents, as the services send them and the CLI prints them. The
/// core parses and prints JSON itself, so both platforms behave the same:
/// integers stay integers, text stays UTF-8, and nothing is left out.

import Foundation

public enum JSON: Sendable, Equatable {
    case null
    case bool(Bool)
    case int(Int64)
    case double(Double)
    case string(String)
    case array([JSON])
    case object([String: JSON])
}

public struct JSONError: Error, CustomStringConvertible {
    public let message: String
    public var description: String { message }
}

// MARK: - Reading

extension JSON {
    public var isNull: Bool {
        if case .null = self { return true }
        return false
    }

    public var bool: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }

    /// An integer literal; a number with a fraction or exponent is not one.
    public var int: Int? {
        if case .int(let value) = self { return Int(exactly: value) }
        return nil
    }

    public var string: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    public var array: [JSON]? {
        if case .array(let value) = self { return value }
        return nil
    }

    public var object: [String: JSON]? {
        if case .object(let value) = self { return value }
        return nil
    }

    /// The member of an object, or nil for anything else.
    public subscript(key: String) -> JSON? {
        object?[key]
    }

    /// The element of an array, or nil for anything else.
    public subscript(index: Int) -> JSON? {
        guard let array, array.indices.contains(index) else { return nil }
        return array[index]
    }

    /// A string member, or `fallback` when it is missing or not a string.
    public func string(_ key: String, or fallback: String) -> String {
        self[key]?.string ?? fallback
    }
}

extension Optional where Wrapped == JSON {
    public subscript(key: String) -> JSON? { self?[key] }
    public var string: String? { self?.string }
    public var int: Int? { self?.int }
    public var bool: Bool? { self?.bool }
    public var array: [JSON]? { self?.array }
    public var object: [String: JSON]? { self?.object }
}

// MARK: - Building

extension JSON: ExpressibleByStringLiteral, ExpressibleByBooleanLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral, ExpressibleByNilLiteral
{
    public init(stringLiteral value: String) { self = .string(value) }
    public init(booleanLiteral value: Bool) { self = .bool(value) }
    public init(integerLiteral value: Int64) { self = .int(value) }
    public init(arrayLiteral elements: JSON...) { self = .array(elements) }
    public init(dictionaryLiteral elements: (String, JSON)...) {
        self = .object(Dictionary(elements, uniquingKeysWith: { _, last in last }))
    }
    public init(nilLiteral: ()) { self = .null }

    /// A string, or null for nil.
    public static func string(_ value: String?) -> JSON {
        value.map { JSON.string($0) } ?? .null
    }

    public static func int(_ value: Int?) -> JSON {
        value.map { JSON.int(Int64($0)) } ?? .null
    }
}

// MARK: - Parsing

extension JSON {
    public static func parse(_ data: Data) throws -> JSON {
        var parser = Parser(bytes: [UInt8](data))
        return try parser.document()
    }

    public static func parse(_ text: String) throws -> JSON {
        var parser = Parser(bytes: Array(text.utf8))
        return try parser.document()
    }

    private struct Parser {
        let bytes: [UInt8]
        var index = 0

        init(bytes: [UInt8]) {
            self.bytes = bytes
        }

        mutating func document() throws -> JSON {
            skipWhitespace()
            let value = try self.value()
            skipWhitespace()
            guard index == bytes.count else { throw error("unexpected text after the document") }
            return value
        }

        private func error(_ message: String) -> JSONError {
            JSONError(message: "Invalid JSON at byte \(index): \(message).")
        }

        private var current: UInt8? {
            index < bytes.count ? bytes[index] : nil
        }

        private mutating func skipWhitespace() {
            while let byte = current, byte == 0x20 || byte == 0x09 || byte == 0x0A || byte == 0x0D {
                index += 1
            }
        }

        private mutating func expect(_ literal: String) throws {
            for byte in literal.utf8 {
                guard current == byte else { throw error("expected \(literal)") }
                index += 1
            }
        }

        private mutating func value() throws -> JSON {
            guard let byte = current else { throw error("unexpected end") }
            switch byte {
            case UInt8(ascii: "{"): return try object()
            case UInt8(ascii: "["): return try array()
            case UInt8(ascii: "\""): return .string(try string())
            case UInt8(ascii: "t"): try expect("true"); return .bool(true)
            case UInt8(ascii: "f"): try expect("false"); return .bool(false)
            case UInt8(ascii: "n"): try expect("null"); return .null
            case UInt8(ascii: "-"), UInt8(ascii: "0")...UInt8(ascii: "9"): return try number()
            default: throw error("unexpected character")
            }
        }

        private mutating func object() throws -> JSON {
            index += 1
            var members: [String: JSON] = [:]
            skipWhitespace()
            if current == UInt8(ascii: "}") {
                index += 1
                return .object(members)
            }
            while true {
                skipWhitespace()
                guard current == UInt8(ascii: "\"") else { throw error("expected a member name") }
                let name = try string()
                skipWhitespace()
                guard current == UInt8(ascii: ":") else { throw error("expected ':'") }
                index += 1
                skipWhitespace()
                members[name] = try value()
                skipWhitespace()
                switch current {
                case UInt8(ascii: ","): index += 1
                case UInt8(ascii: "}"): index += 1; return .object(members)
                default: throw error("expected ',' or '}'")
                }
            }
        }

        private mutating func array() throws -> JSON {
            index += 1
            var elements: [JSON] = []
            skipWhitespace()
            if current == UInt8(ascii: "]") {
                index += 1
                return .array(elements)
            }
            while true {
                skipWhitespace()
                elements.append(try value())
                skipWhitespace()
                switch current {
                case UInt8(ascii: ","): index += 1
                case UInt8(ascii: "]"): index += 1; return .array(elements)
                default: throw error("expected ',' or ']'")
                }
            }
        }

        private mutating func number() throws -> JSON {
            let start = index
            var isInteger = true
            if current == UInt8(ascii: "-") { index += 1 }
            guard let first = current, first >= UInt8(ascii: "0"), first <= UInt8(ascii: "9") else {
                throw error("expected a digit")
            }
            if first == UInt8(ascii: "0"), index + 1 < bytes.count, bytes[index + 1] >= UInt8(ascii: "0"),
                bytes[index + 1] <= UInt8(ascii: "9")
            {
                throw error("a leading zero")
            }
            while let byte = current, byte >= UInt8(ascii: "0"), byte <= UInt8(ascii: "9") { index += 1 }
            if current == UInt8(ascii: ".") {
                isInteger = false
                index += 1
                guard let byte = current, byte >= UInt8(ascii: "0"), byte <= UInt8(ascii: "9") else {
                    throw error("expected a digit after '.'")
                }
                while let byte = current, byte >= UInt8(ascii: "0"), byte <= UInt8(ascii: "9") { index += 1 }
            }
            if current == UInt8(ascii: "e") || current == UInt8(ascii: "E") {
                isInteger = false
                index += 1
                if current == UInt8(ascii: "+") || current == UInt8(ascii: "-") { index += 1 }
                guard let byte = current, byte >= UInt8(ascii: "0"), byte <= UInt8(ascii: "9") else {
                    throw error("expected a digit in the exponent")
                }
                while let byte = current, byte >= UInt8(ascii: "0"), byte <= UInt8(ascii: "9") { index += 1 }
            }
            let text = String(decoding: bytes[start..<index], as: UTF8.self)
            if isInteger, let value = Int64(text) {
                return .int(value)
            }
            guard let value = Double(text) else { throw error("not a number") }
            return .double(value)
        }

        private mutating func hex4() throws -> UInt32 {
            guard index + 4 <= bytes.count,
                let value = UInt32(String(decoding: bytes[index..<index + 4], as: UTF8.self), radix: 16)
            else { throw error("expected four hex digits") }
            index += 4
            return value
        }

        private mutating func string() throws -> String {
            index += 1
            var out: [UInt8] = []
            while true {
                guard let byte = current else { throw error("unterminated string") }
                index += 1
                switch byte {
                case UInt8(ascii: "\""):
                    return String(decoding: out, as: UTF8.self)
                case UInt8(ascii: "\\"):
                    guard let escaped = current else { throw error("unterminated escape") }
                    index += 1
                    switch escaped {
                    case UInt8(ascii: "\""): out.append(0x22)
                    case UInt8(ascii: "\\"): out.append(0x5C)
                    case UInt8(ascii: "/"): out.append(0x2F)
                    case UInt8(ascii: "b"): out.append(0x08)
                    case UInt8(ascii: "f"): out.append(0x0C)
                    case UInt8(ascii: "n"): out.append(0x0A)
                    case UInt8(ascii: "r"): out.append(0x0D)
                    case UInt8(ascii: "t"): out.append(0x09)
                    case UInt8(ascii: "u"):
                        var scalar = try hex4()
                        if (0xD800...0xDBFF).contains(scalar) {
                            // A surrogate pair: the low half follows as another escape.
                            guard current == UInt8(ascii: "\\"), index + 1 < bytes.count,
                                bytes[index + 1] == UInt8(ascii: "u")
                            else { throw error("a lone high surrogate") }
                            index += 2
                            let low = try hex4()
                            guard (0xDC00...0xDFFF).contains(low) else { throw error("a lone high surrogate") }
                            scalar = 0x10000 + ((scalar - 0xD800) << 10) + (low - 0xDC00)
                        }
                        let character = Unicode.Scalar(scalar) ?? "\u{FFFD}"
                        out.append(contentsOf: Array(String(Character(character)).utf8))
                    default:
                        throw error("unknown escape")
                    }
                case 0x00..<0x20:
                    throw error("a control character in a string")
                default:
                    out.append(byte)
                }
            }
        }
    }
}

// MARK: - Printing

extension JSON {
    /// The document as text: one line, keys sorted, UTF-8 kept as is.
    public func serialized(indent: Int? = nil) -> String {
        var out = ""
        write(to: &out, indent: indent, depth: 0)
        return out
    }

    public var data: Data {
        Data(serialized().utf8)
    }

    private func write(to out: inout String, indent: Int?, depth: Int) {
        func newline(_ level: Int) {
            guard let indent else { return }
            out += "\n" + String(repeating: " ", count: indent * level)
        }
        switch self {
        case .null:
            out += "null"
        case .bool(let value):
            out += value ? "true" : "false"
        case .int(let value):
            out += String(value)
        case .double(let value):
            out += value.isFinite ? String(value) : "null"
        case .string(let value):
            JSON.writeString(value, to: &out)
        case .array(let elements):
            guard !elements.isEmpty else { out += "[]"; return }
            out += "["
            for (position, element) in elements.enumerated() {
                if position > 0 { out += "," }
                newline(depth + 1)
                element.write(to: &out, indent: indent, depth: depth + 1)
            }
            newline(depth)
            out += "]"
        case .object(let members):
            guard !members.isEmpty else { out += "{}"; return }
            out += "{"
            for (position, key) in members.keys.sorted().enumerated() {
                if position > 0 { out += "," }
                newline(depth + 1)
                JSON.writeString(key, to: &out)
                out += indent == nil ? ":" : ": "
                members[key]!.write(to: &out, indent: indent, depth: depth + 1)
            }
            newline(depth)
            out += "}"
        }
    }

    private static func writeString(_ value: String, to out: inout String) {
        out += "\""
        for scalar in value.unicodeScalars {
            switch scalar {
            case "\"": out += "\\\""
            case "\\": out += "\\\\"
            case "\n": out += "\\n"
            case "\r": out += "\\r"
            case "\t": out += "\\t"
            case "\u{08}": out += "\\b"
            case "\u{0C}": out += "\\f"
            case "\u{00}"..."\u{1F}":
                let hex = String(scalar.value, radix: 16, uppercase: true)
                out += "\\u" + String(repeating: "0", count: 4 - hex.count) + hex
            default:
                out.unicodeScalars.append(scalar)
            }
        }
        out += "\""
    }
}
