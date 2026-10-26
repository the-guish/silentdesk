/// The SQLCipher database. See docs/specs/storage.md.

import Foundation

final class SqlcipherDatabase: Database, @unchecked Sendable {
    /// The keyring entry holding the database key.
    static let keyName = "database-key"

    let path: String
    private let keyring: any Keyring
    private let migrations: [Migrations.Migration]
    // One operation at a time; the connection is opened by the first.
    private let lock = NSLock()
    private var connection: SQLiteConnection?

    init(path: String, keyring: any Keyring, migrations: [Migrations.Migration] = Migrations.all) {
        self.path = path
        self.keyring = keyring
        self.migrations = migrations
    }

    func transaction<T>(_ body: (any DatabaseConnection) throws -> T) throws -> T {
        lock.lock()
        defer { lock.unlock() }
        let connection = try open()
        try storage { try connection.execute("BEGIN") }
        do {
            let result = try body(connection)
            try storage { try connection.execute("COMMIT") }
            return result
        } catch {
            try? connection.execute("ROLLBACK")
            throw error
        }
    }

    private func open() throws -> SQLiteConnection {
        if let connection {
            return connection
        }
        let connection = try connect()
        try migrate(connection)
        self.connection = connection
        return connection
    }

    private func connect() throws -> SQLiteConnection {
        var key = try keyring.get(Self.keyName)
        if key == nil {
            if FileManager.default.fileExists(atPath: path) {
                throw StorageError("The database \(path) cannot be opened: its key is missing from the keyring.")
            }
            let fresh = Base64.randomBytes(32).map { String(format: "%02x", $0) }.joined()
            try keyring.set(Self.keyName, fresh)
            key = fresh
        }
        guard let key else { throw StorageError("The database key is missing.") }

        let directory = (path as NSString).deletingLastPathComponent
        do {
            try FileManager.default.createDirectory(
                atPath: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            // Created readable by the user only, before SQLCipher writes to it.
            if !FileManager.default.fileExists(atPath: path) {
                guard FileManager.default.createFile(atPath: path, contents: nil, attributes: [.posixPermissions: 0o600])
                else { throw StorageError("The database \(path) cannot be created.") }
            }
        } catch let error as StorageError {
            throw error
        } catch {
            throw StorageError("The data folder \(directory) cannot be created: \(error).")
        }

        let connection = try storage { try SQLiteConnection(path: path) }
        try storage { try connection.execute("PRAGMA cipher_log_level = NONE") }
        try storage { try connection.execute("PRAGMA key = \"x'\(key)'\"") }
        do {
            _ = try connection.query("SELECT count(*) FROM sqlite_master")
        } catch {
            throw StorageError("The database \(path) cannot be opened: \(error).")
        }
        try storage { try connection.execute("PRAGMA foreign_keys = ON") }
        return connection
    }

    /// Runs the migrations above the database's user_version, in one transaction.
    private func migrate(_ connection: SQLiteConnection) throws {
        let current = try storage { try connection.queryOne("PRAGMA user_version")?.first?.int ?? 0 }
        let pending = migrations.filter { Int64($0.number) > current }.sorted { $0.number < $1.number }
        guard let last = pending.last else { return }
        let script = pending.map { $0.sql + "\n" }.joined()
        do {
            try connection.executeScript("BEGIN;\n\(script)\nPRAGMA user_version = \(last.number);\nCOMMIT;")
        } catch {
            if connection.isInTransaction {
                try? connection.execute("ROLLBACK")
            }
            throw StorageError("The database \(path) could not be migrated: \(error).")
        }
    }

    /// Reports a SQLite failure as a storage error.
    private func storage<T>(_ body: () throws -> T) throws -> T {
        do {
            return try body()
        } catch let error as SQLiteError {
            throw StorageError("The database \(path) failed: \(error.message).")
        }
    }
}
