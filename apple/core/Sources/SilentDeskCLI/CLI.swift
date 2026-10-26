import Foundation
import SilentDeskCore

/// `silentdesk`: the JSON command line specified in docs/specs/cli.md. Each command
/// is a thin wrapper around the matching function in `API`.
public enum CLI {
    public static let exitOK: Int32 = 0
    public static let exitFailed: Int32 = 1
    public static let exitUsage: Int32 = 2

    public static let commands = ["connect", "delete", "disconnect", "history", "reply", "services", "sync", "topics", "version"]

    /// What one run prints to stdout, and the code it exits with.
    public struct Result: Sendable {
        public let exitCode: Int32
        public let output: Data
    }

    /// Runs one command line, without the program name. `stdin` reads the
    /// whole standard input, for the commands that take it.
    public static func run(_ arguments: [String], stdin: () -> String = readStandardInput) async -> Result {
        let names = commands.joined(separator: ", ")
        do {
            guard let command = arguments.first else {
                throw UsageError(message: "Missing command. Commands: \(names).")
            }
            let args = Array(arguments.dropFirst())
            let document: JSON
            switch command {
            case "version":
                try noArguments(command, args)
                document = Documents.version(API.version())
            case "services":
                try noArguments(command, args)
                document = .array(try await API.desk().services().map(Documents.status))
            case "topics":
                try noArguments(command, args)
                document = .array(try await API.desk().topics().map(Documents.topic))
            case "connect":
                let service = try oneService(command, args)
                let fields = try connectFields(stdin())
                document = Documents.status(try await API.desk().connect(service, params: fields))
            case "disconnect":
                let service = try oneService(command, args)
                document = Documents.status(try await API.desk().disconnect(service))
            case "sync":
                guard args.count <= 1 else { throw UsageError(message: "sync takes at most one service name.") }
                let desk = API.desk()
                try await desk.sync(args.first)
                document = ["lastSynced": .string(try await desk.lastSynced())]
            case "reply":
                guard args.count == 1 else { throw UsageError(message: "reply takes one topic ID; the reply comes on stdin.") }
                let body = stdin()
                guard !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                    throw UsageError(message: "The reply is empty: write it on stdin.")
                }
                try await API.desk().reply(topicID: args[0], body: body)
                document = [:]
            case "history":
                guard args.count == 1 else { throw UsageError(message: "history takes one topic ID.") }
                document = .array(try await API.desk().history(topicID: args[0]).map(Documents.message))
            case "delete":
                guard args.count == 1 || args.count == 2 else {
                    throw UsageError(message: "delete takes one topic ID, and optionally one of its item keys.")
                }
                if args.count == 2 {
                    try await API.desk().deleteItem(topicID: args[0], itemKey: args[1])
                } else {
                    try await API.desk().delete(topicID: args[0])
                }
                document = [:]
            default:
                throw UsageError(message: "Unknown command '\(command)'. Commands: \(names).")
            }
            return Result(exitCode: exitOK, output: document.data)
        } catch let error as UsageError {
            return failure(exitUsage, kind: "usage", message: error.message)
        } catch let error as UnknownService {
            return failure(exitUsage, kind: "usage", message: error.message)
        } catch let error as UnknownTopic {
            return failure(exitUsage, kind: "usage", message: error.message)
        } catch let error as UnknownItem {
            return failure(exitUsage, kind: "usage", message: error.message)
        } catch let error as EmptyReply {
            return failure(exitUsage, kind: "usage", message: error.message)
        } catch let error as ConnectorError {
            return failure(exitFailed, kind: error.kind.rawValue, message: error.message)
        } catch let error as SyncFailed {
            let failures = error.failures.map { failure -> JSON in
                let kind = (failure.error as? ConnectorError)?.kind.rawValue ?? "internal"
                return ["service": .string(failure.service), "kind": .string(kind), "message": .string(describe(failure.error))]
            }
            return failure(exitFailed, kind: "sync", message: error.message, failures: .array(failures))
        } catch let error as StorageError {
            return failure(exitFailed, kind: "storage", message: error.message)
        } catch {
            // Every failure must still print a JSON document.
            FileHandle.standardError.write(Data("\(error)\n".utf8))
            return failure(exitFailed, kind: "internal", message: describe(error))
        }
    }

    public static func readStandardInput() -> String {
        String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self)
    }

    private static func noArguments(_ command: String, _ args: [String]) throws {
        guard args.isEmpty else { throw UsageError(message: "\(command) takes no arguments.") }
    }

    private static func oneService(_ command: String, _ args: [String]) throws -> String {
        guard args.count == 1 else { throw UsageError(message: "\(command) takes one service name.") }
        return args[0]
    }

    /// The connect fields: one JSON object of strings, or nothing.
    static func connectFields(_ text: String) throws -> [String: String] {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [:] }
        let document: JSON
        do {
            document = try JSON.parse(text)
        } catch {
            throw UsageError(message: "The connect fields on stdin are not JSON: \(error).")
        }
        guard let object = document.object else {
            throw UsageError(message: "The connect fields on stdin must be one JSON object of strings.")
        }
        var fields: [String: String] = [:]
        for (name, value) in object {
            guard let text = value.string else {
                throw UsageError(message: "The connect fields on stdin must be one JSON object of strings.")
            }
            fields[name] = text
        }
        return fields
    }

    private static func describe(_ error: any Error) -> String {
        let text = "\(error)"
        return text.isEmpty ? String(describing: type(of: error)) : text
    }

    static func failure(_ exitCode: Int32, kind: String, message: String, failures: JSON? = nil) -> Result {
        var body: [String: JSON] = ["kind": .string(kind), "message": .string(message)]
        if let failures {
            body["failures"] = failures
        }
        return Result(exitCode: exitCode, output: JSON.object(["error": .object(body)]).data)
    }
}

struct UsageError: Error {
    let message: String
}

/// The contract's documents, built from the core's data (spec/schema).
enum Documents {
    static func version(_ version: Version) -> JSON {
        [
            "contract": .int(Int64(version.contract)),
            "implementation": .string(version.implementation),
            "version": .string(version.version),
        ]
    }

    static func status(_ status: ServiceStatus) -> JSON {
        [
            "service": .string(status.service),
            "configured": .bool(status.configured),
            "connected": .bool(status.connected),
            "account": .string(status.account),
        ]
    }

    static func item(_ item: Item) -> JSON {
        [
            "key": .string(item.key),
            "direction": .string(item.direction?.rawValue),
            "author": .string(item.author),
            "url": .string(item.url),
            "date": .string(item.date),
            "deletable": .bool(item.deletable),
        ]
    }

    static func topic(_ topic: TopicView) -> JSON {
        [
            "id": .string(topic.id),
            "service": .string(topic.service),
            "title": .string(topic.title),
            "items": .array(topic.items.map(item)),
            "updatedAt": .string(topic.updatedAt),
            "deletable": .bool(topic.deletable),
            "projectId": .string(topic.projectId),
        ]
    }

    static func message(_ message: Message) -> JSON {
        [
            "key": .string(message.key),
            "direction": .string(message.direction?.rawValue),
            "author": .string(message.author),
            "text": .string(message.text),
            "date": .string(message.date),
        ]
    }
}
