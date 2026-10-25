/// JSON documents, as the services send them and the CLI prints them: one
/// value type, read and written through Foundation's coders. Integers stay
/// integers, text stays UTF-8, and a null is printed, never left out.

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

    /// A whole number. The coder reads 1.0 as 1 too; the contract leaves
    /// number formatting open.
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

// MARK: - Parsing and printing

extension JSON: Codable {
    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int64.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSON].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSON].self))
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let value): try container.encode(value)
        case .int(let value): try container.encode(value)
        case .double(let value):
            // JSON has no infinity or NaN.
            if value.isFinite { try container.encode(value) } else { try container.encodeNil() }
        case .string(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        }
    }

    public static func parse(_ data: Data) throws -> JSON {
        do {
            return try JSONDecoder().decode(JSON.self, from: data)
        } catch {
            throw JSONError(message: "Not a JSON document: \(error.localizedDescription)")
        }
    }

    public static func parse(_ text: String) throws -> JSON {
        try parse(Data(text.utf8))
    }

    /// The document as text: keys sorted, UTF-8 kept as is, slashes unescaped,
    /// on one line unless `pretty`.
    public func serialized(pretty: Bool = false) -> String {
        String(decoding: data(pretty: pretty), as: UTF8.self)
    }

    public var data: Data {
        data(pretty: false)
    }

    private func data(pretty: Bool) -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = pretty
            ? [.sortedKeys, .withoutEscapingSlashes, .prettyPrinted] : [.sortedKeys, .withoutEscapingSlashes]
        // Every case encodes, non-finite numbers as null, so this cannot fail.
        return (try? encoder.encode(self)) ?? Data("null".utf8)
    }
}
