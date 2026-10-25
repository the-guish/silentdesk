// The embedded migrations must be the ones in spec/sql, byte for byte apart
// from trailing whitespace: Scripts/sync-migrations.sh regenerates them.
import Foundation
@testable import SilentDeskCore
import Testing

private func trimmed(_ text: String) -> String {
    text.trimmingCharacters(in: .whitespacesAndNewlines)
}

@Test func embeddedMigrationsMatchTheSpec() throws {
    let specSQL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("spec").appendingPathComponent("sql")
    let files = try FileManager.default.contentsOfDirectory(atPath: specSQL.path).filter { $0.hasSuffix(".sql") }.sorted()
    #expect(files.map { String($0.dropLast(4)) } == Migrations.all.map(\.name))
    for (file, migration) in zip(files, Migrations.all) {
        let text = try String(contentsOf: specSQL.appendingPathComponent(file), encoding: .utf8)
        #expect(trimmed(text) == trimmed(migration.sql), "\(file) differs: run Scripts/sync-migrations.sh")
        #expect(Int(file.prefix(4)) == migration.number)
    }
}

@Test func migrationsAreNumberedInOrder() {
    let numbers = Migrations.all.map(\.number)
    #expect(numbers == Array(1...numbers.count))
}
