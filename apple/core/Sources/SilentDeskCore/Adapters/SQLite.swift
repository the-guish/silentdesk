/// A thin layer over SQLCipher's C API: one connection, statements with
/// parameters, rows as values. The database is keyed with PRAGMA key, so
/// only the standard SQLite API is needed, which Zetetic's framework exposes.

import Foundation
#if canImport(SQLCipher)
import SQLCipher
#else
import CSQLCipher
#endif

struct SQLiteError: Error, CustomStringConvertible {
    let code: Int32
    let message: String
    var description: String { message }
}

// SQLite copies the bound text, so Swift's strings may go.
private let transientDestructor = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

final class SQLiteConnection: DatabaseConnection {
    private let handle: OpaquePointer

    init(path: String) throws {
        var handle: OpaquePointer?
        let code = sqlite3_open_v2(path, &handle, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil)
        guard code == SQLITE_OK, let handle else {
            let message = handle.map { String(cString: sqlite3_errmsg($0)) } ?? "the database could not be opened"
            if let handle { sqlite3_close_v2(handle) }
            throw SQLiteError(code: code, message: message)
        }
        self.handle = handle
    }

    deinit {
        sqlite3_close_v2(handle)
    }

    var isInTransaction: Bool {
        sqlite3_get_autocommit(handle) == 0
    }

    private var lastError: SQLiteError {
        SQLiteError(code: sqlite3_errcode(handle), message: String(cString: sqlite3_errmsg(handle)))
    }

    func execute(_ sql: String, _ parameters: [SQLValue]) throws {
        _ = try query(sql, parameters)
    }

    func query(_ sql: String, _ parameters: [SQLValue]) throws -> [[SQLValue]] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK, let statement else { throw lastError }
        defer { sqlite3_finalize(statement) }
        for (index, value) in parameters.enumerated() {
            let slot = Int32(index + 1)
            let code: Int32
            switch value {
            case .null:
                code = sqlite3_bind_null(statement, slot)
            case .integer(let number):
                code = sqlite3_bind_int64(statement, slot, number)
            case .real(let number):
                code = sqlite3_bind_double(statement, slot, number)
            case .text(let text):
                code = sqlite3_bind_text(statement, slot, text, -1, transientDestructor)
            case .blob(let data):
                code = data.withUnsafeBytes { bytes in
                    sqlite3_bind_blob(statement, slot, bytes.baseAddress, Int32(data.count), transientDestructor)
                }
            }
            guard code == SQLITE_OK else { throw lastError }
        }
        var rows: [[SQLValue]] = []
        while true {
            switch sqlite3_step(statement) {
            case SQLITE_ROW:
                rows.append(row(of: statement))
            case SQLITE_DONE:
                return rows
            default:
                throw lastError
            }
        }
    }

    /// Runs a script of several statements, such as a migration.
    func executeScript(_ sql: String) throws {
        var message: UnsafeMutablePointer<CChar>?
        let code = sqlite3_exec(handle, sql, nil, nil, &message)
        guard code == SQLITE_OK else {
            let text = message.map { String(cString: $0) } ?? "the script failed"
            sqlite3_free(message)
            throw SQLiteError(code: code, message: text)
        }
    }

    private func row(of statement: OpaquePointer) -> [SQLValue] {
        (0..<sqlite3_column_count(statement)).map { column in
            switch sqlite3_column_type(statement, column) {
            case SQLITE_INTEGER:
                return .integer(sqlite3_column_int64(statement, column))
            case SQLITE_FLOAT:
                return .real(sqlite3_column_double(statement, column))
            case SQLITE_TEXT:
                return .text(String(cString: sqlite3_column_text(statement, column)))
            case SQLITE_BLOB:
                let count = Int(sqlite3_column_bytes(statement, column))
                guard count > 0, let bytes = sqlite3_column_blob(statement, column) else { return .blob(Data()) }
                return .blob(Data(bytes: bytes, count: count))
            default:
                return .null
            }
        }
    }
}
