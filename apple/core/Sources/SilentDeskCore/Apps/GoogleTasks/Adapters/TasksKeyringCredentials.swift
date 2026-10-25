final class TasksKeyringCredentials: TasksCredentials {
    /// The keyring entry per service, as in legacy. See spec/storage.md.
    static let names = ["tasks": "google-tasks-refresh-token"]

    private let keyring: any Keyring

    init(keyring: any Keyring) {
        self.keyring = keyring
    }

    private func name(_ service: String) -> String {
        Self.names[service] ?? "google-\(service)-refresh-token"
    }

    func refreshToken(_ service: String) throws -> String? {
        try keyring.get(name(service))
    }

    func saveRefreshToken(_ service: String, _ token: String) throws {
        try keyring.set(name(service), token)
    }

    func deleteRefreshToken(_ service: String) throws {
        try keyring.delete(name(service))
    }
}
