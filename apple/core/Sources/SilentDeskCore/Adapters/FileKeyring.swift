/// A keyring in a plain JSON file, for tests only: it stores secrets
/// unencrypted. Used when SILENTDESK_TEST_KEYRING is set; see spec/cli.md.

import Foundation

final class FileKeyring: Keyring {
    let path: String

    init(path: String) {
        self.path = path
    }

    func get(_ name: String) throws -> String? {
        try read()[name]
    }

    func set(_ name: String, _ value: String) throws {
        var entries = try read()
        entries[name] = value
        try write(entries)
    }

    func delete(_ name: String) throws {
        var entries = try read()
        if entries.removeValue(forKey: name) != nil {
            try write(entries)
        }
    }

    private func read() throws -> [String: String] {
        guard FileManager.default.fileExists(atPath: path) else { return [:] }
        guard let data = FileManager.default.contents(atPath: path) else {
            throw StorageError("The keyring file \(path) cannot be read.")
        }
        do {
            let entries = try JSON.parse(data).object ?? [:]
            return entries.compactMapValues(\.string)
        } catch {
            throw StorageError("The keyring file \(path) is not a JSON object: \(error).")
        }
    }

    private func write(_ entries: [String: String]) throws {
        let directory = (path as NSString).deletingLastPathComponent
        if !directory.isEmpty {
            try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
        }
        let document = JSON.object(entries.mapValues { JSON.string($0) })
        // Readable by the user only, like the real credential store.
        let written = FileManager.default.createFile(
            atPath: path, contents: Data((document.serialized(indent: 2) + "\n").utf8),
            attributes: [.posixPermissions: 0o600])
        guard written else { throw StorageError("The keyring file \(path) cannot be written.") }
    }
}
