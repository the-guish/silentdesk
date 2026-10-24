/// The core's public API: one function per command in spec/cli.md.
///
/// The CLI and the apps use only this. Everything it returns is plain data,
/// shaped as the contract describes.
public enum API {
    /// The version of spec/cli.md this core implements.
    public static let contract = 1
    /// This core's own version.
    public static let coreVersion = "0.1.0"

    public static func version() -> Version {
        Version(contract: contract, implementation: "swift", version: coreVersion)
    }
}

public struct Version: Codable, Equatable, Sendable {
    public let contract: Int
    public let implementation: String
    public let version: String
}
