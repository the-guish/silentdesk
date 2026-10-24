// Unit tests for the CLI. Behaviour shared with the Python core is tested by
// the conformance suite in spec/; these cover what it cannot see.
import Foundation
@testable import SilentDeskCLI
import Testing

private func document(_ result: CLI.Result) throws -> [String: Any] {
    try #require(JSONSerialization.jsonObject(with: result.output) as? [String: Any])
}

@Test func usageErrorsListTheCommands() throws {
    let result = CLI.run(["no-such-command"])
    #expect(result.exitCode == CLI.exitUsage)
    let error = try #require(document(result)["error"] as? [String: String])
    #expect(error == ["kind": "usage", "message": "Unknown command 'no-such-command'. Commands: version."])
}

@Test func versionPrintsOneJSONObject() throws {
    let result = CLI.run(["version"])
    #expect(result.exitCode == CLI.exitOK)
    #expect(try document(result)["implementation"] as? String == "swift")
}
