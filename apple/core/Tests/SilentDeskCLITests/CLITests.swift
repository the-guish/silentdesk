// Unit tests for the CLI. Behaviour shared with the Python core is tested by
// the conformance suite in spec/; these cover what it cannot see.
import Foundation
@testable import SilentDeskCLI
import SilentDeskCore
import Testing

private func document(_ result: CLI.Result) throws -> [String: Any] {
    try #require(JSONSerialization.jsonObject(with: result.output) as? [String: Any])
}

@Test func usageErrorsListTheCommands() async throws {
    let result = await CLI.run(["no-such-command"]) { "" }
    #expect(result.exitCode == CLI.exitUsage)
    let error = try #require(document(result)["error"] as? [String: String])
    #expect(error == [
        "kind": "usage",
        "message": "Unknown command 'no-such-command'. Commands: connect, delete, disconnect, history, reply, services, sync, topics, version.",
    ])
}

@Test func aMissingCommandIsAUsageError() async throws {
    let result = await CLI.run([]) { "" }
    #expect(result.exitCode == CLI.exitUsage)
    #expect((try document(result)["error"] as? [String: String])?["kind"] == "usage")
}

@Test func versionPrintsOneJSONObject() async throws {
    let result = await CLI.run(["version"]) { "" }
    #expect(result.exitCode == CLI.exitOK)
    #expect(try document(result)["implementation"] as? String == "swift")
    #expect(try document(result)["contract"] as? Int == API.contract)
    #expect(!String(decoding: result.output, as: UTF8.self).hasSuffix("\n"), "the program adds the newline")
}

@Test func commandsCheckTheirArgumentsBeforeTouchingAnything() async throws {
    for arguments in [["version", "x"], ["services", "x"], ["topics", "x"], ["connect"], ["disconnect", "a", "b"], ["sync", "a", "b"], ["reply"], ["history"], ["delete"], ["delete", "a", "b", "c"]] {
        let result = await CLI.run(arguments) { "" }
        #expect(result.exitCode == CLI.exitUsage, "\(arguments)")
    }
}

@Test func anEmptyReplyIsAUsageError() async throws {
    let result = await CLI.run(["reply", "some-topic"]) { "  \n" }
    #expect(result.exitCode == CLI.exitUsage)
}

@Test func connectFieldsMustBeOneObjectOfStrings() throws {
    #expect(try CLI.connectFields("") == [:])
    #expect(try CLI.connectFields("  \n") == [:])
    #expect(try CLI.connectFields(#"{"token": "t", "server": ""}"#) == ["token": "t", "server": ""])
    #expect(throws: UsageError.self) { try CLI.connectFields("[\"token\"]") }
    #expect(throws: UsageError.self) { try CLI.connectFields(#"{"token": 1}"#) }
    #expect(throws: UsageError.self) { try CLI.connectFields("not json") }
}

@Test func failuresAreErrorDocuments() throws {
    let result = CLI.failure(CLI.exitFailed, kind: "sync", message: "1 service failed to sync.", failures: [
        ["service": "github", "kind": "auth", "message": "Rejected."]
    ])
    #expect(result.exitCode == CLI.exitFailed)
    let error = try #require(document(result)["error"] as? [String: Any])
    #expect(error["kind"] as? String == "sync")
    #expect((error["failures"] as? [[String: String]])?.first?["service"] == "github")
}
