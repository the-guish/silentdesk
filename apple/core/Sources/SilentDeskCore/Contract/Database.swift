/// The one database file every app keeps its own tables in. See docs/specs/storage.md.

import Foundation

/// One SQL value, as SQLite stores it.
enum SQLValue: Sendable, Equatable {
    case null
    case integer(Int64)
    case real(Double)
    case text(String)
    case blob(Data)

    var string: String? {
        if case .text(let value) = self { return value }
        return nil
    }

    var int: Int64? {
        if case .integer(let value) = self { return value }
        return nil
    }

    var bool: Bool {
        if case .integer(let value) = self { return value != 0 }
        return false
    }

    var isNull: Bool {
        if case .null = self { return true }
        return false
    }

    /// Text, or NULL for nil.
    static func text(_ value: String?) -> SQLValue {
        value.map { SQLValue.text($0) } ?? .null
    }

    static func bool(_ value: Bool) -> SQLValue {
        .integer(value ? 1 : 0)
    }
}

/// A connection inside one transaction.
protocol DatabaseConnection {
    /// Runs one statement, with `?` parameters.
    func execute(_ sql: String, _ parameters: [SQLValue]) throws
    /// Runs one query and returns every row.
    func query(_ sql: String, _ parameters: [SQLValue]) throws -> [[SQLValue]]
}

extension DatabaseConnection {
    func execute(_ sql: String) throws {
        try execute(sql, [])
    }

    func query(_ sql: String) throws -> [[SQLValue]] {
        try query(sql, [])
    }

    func queryOne(_ sql: String, _ parameters: [SQLValue] = []) throws -> [SQLValue]? {
        try query(sql, parameters).first
    }
}

protocol Database: Sendable {
    /// Runs `body` on a connection inside one transaction: committed when it
    /// returns, rolled back if it throws. Opens and migrates the database on
    /// first use, and throws StorageError if it cannot.
    func transaction<T>(_ body: (any DatabaseConnection) throws -> T) throws -> T
}
