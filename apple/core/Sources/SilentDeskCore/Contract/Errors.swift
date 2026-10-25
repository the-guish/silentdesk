/// Errors apps raise to each other and to the interfaces. Each connector
/// error has a `kind`, which the CLI reports as the error kind in spec/cli.md.

/// A failure in one connector, or below any one app, as in the HTTPS client.
public struct ConnectorError: Error, Sendable, Equatable {
    public enum Kind: String, Sendable {
        /// The service is not connected, or it rejected the credentials.
        case auth
        /// The service could not be reached, or its answer could not be read.
        case network
        /// The service answered with an error.
        case remote
        /// The service cannot do this, such as replying to a task.
        case unsupported
    }

    public let kind: Kind
    /// Nil when raised below any one app, as by the HTTPS client.
    public let service: String?
    public let message: String
    /// The HTTP status a `remote` error came with, when known.
    public let status: Int?

    public init(kind: Kind, service: String?, message: String, status: Int? = nil) {
        self.kind = kind
        self.service = service
        self.message = message
        self.status = status
    }

    public static func auth(_ service: String?, _ message: String) -> ConnectorError {
        ConnectorError(kind: .auth, service: service, message: message)
    }

    public static func network(_ service: String?, _ message: String) -> ConnectorError {
        ConnectorError(kind: .network, service: service, message: message)
    }

    public static func remote(_ service: String?, _ message: String, status: Int? = nil) -> ConnectorError {
        ConnectorError(kind: .remote, service: service, message: message, status: status)
    }

    public static func unsupported(_ service: String?, _ message: String) -> ConnectorError {
        ConnectorError(kind: .unsupported, service: service, message: message)
    }
}

/// No connector has this service name.
public struct UnknownService: Error, Sendable {
    public let message: String
}

/// No topic has this ID, or its service no longer knows it.
public struct UnknownTopic: Error, Sendable {
    public let message: String
}

/// The topic has no item with this key.
public struct UnknownItem: Error, Sendable {
    public let message: String
}

/// The database cannot be opened, such as when its key is missing, or the
/// credential store cannot be reached.
public struct StorageError: Error, Sendable {
    public let message: String

    public init(_ message: String) {
        self.message = message
    }
}

/// A sync round in which one or more services failed. The others synced.
public struct SyncFailed: Error, Sendable {
    public struct Failure: Sendable {
        public let service: String
        public let error: any Error
    }

    public let failures: [Failure]

    public var message: String {
        "\(failures.count) service\(failures.count == 1 ? "" : "s") failed to sync."
    }
}

extension ConnectorError: CustomStringConvertible {
    public var description: String { message }
}

extension StorageError: CustomStringConvertible {
    public var description: String { message }
}

extension UnknownService: CustomStringConvertible {
    public var description: String { message }
}

extension UnknownTopic: CustomStringConvertible {
    public var description: String { message }
}

extension UnknownItem: CustomStringConvertible {
    public var description: String { message }
}

extension SyncFailed: CustomStringConvertible {
    public var description: String { message }
}
