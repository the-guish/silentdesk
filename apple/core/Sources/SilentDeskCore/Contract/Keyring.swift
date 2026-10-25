/// The OS credential store, where secrets and the database key live. Each
/// method throws StorageError when the store cannot be reached.
protocol Keyring: Sendable {
    func get(_ name: String) throws -> String?
    func set(_ name: String, _ value: String) throws
    func delete(_ name: String) throws
}
