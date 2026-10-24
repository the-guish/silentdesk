import Foundation
import SilentDeskCore

/// `silentdesk`: the JSON command line specified in spec/cli.md. Each
/// command is a thin wrapper around the matching function in `API`.
public enum CLI {
    public static let exitOK: Int32 = 0
    public static let exitFailed: Int32 = 1
    public static let exitUsage: Int32 = 2

    /// What one run prints to stdout, and the code it exits with.
    public struct Result {
        public let exitCode: Int32
        public let output: Data
    }

    static let commands: [(name: String, run: @Sendable ([String]) throws -> any Encodable)] = [
        ("version", { arguments in
            guard arguments.isEmpty else { throw UsageError(message: "version takes no arguments.") }
            return API.version()
        }),
    ]

    /// Runs one command line, without the program name.
    public static func run(_ arguments: [String]) -> Result {
        let names = commands.map(\.name).joined(separator: ", ")
        do {
            guard let command = arguments.first else {
                throw UsageError(message: "Missing command. Commands: \(names).")
            }
            guard let handler = commands.first(where: { $0.name == command }) else {
                throw UsageError(message: "Unknown command '\(command)'. Commands: \(names).")
            }
            return try Result(exitCode: exitOK, output: encode(handler.run(Array(arguments.dropFirst()))))
        } catch let error as UsageError {
            return failure(exitUsage, kind: "usage", message: error.message)
        } catch {
            FileHandle.standardError.write(Data("\(error)\n".utf8))
            return failure(exitFailed, kind: "internal", message: "\(error)")
        }
    }

    static func failure(_ exitCode: Int32, kind: String, message: String) -> Result {
        let document = ErrorDocument(error: .init(kind: kind, message: message))
        // Encoding two strings cannot fail.
        return Result(exitCode: exitCode, output: try! encode(document))
    }

    static func encode(_ document: any Encodable) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return try encoder.encode(document)
    }
}

struct UsageError: Error {
    let message: String
}

struct ErrorDocument: Encodable {
    struct Body: Encodable {
        let kind: String
        let message: String
    }

    let error: Body
}
