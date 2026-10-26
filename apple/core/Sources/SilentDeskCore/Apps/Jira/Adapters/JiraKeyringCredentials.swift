final class JiraKeyringCredentials: JiraCredentials {
    /// The keyring entry, as in legacy: {"email": ..., "token": ...}. See spec/storage.md.
    static let name = "jira-credential"

    private let keyring: any Keyring

    init(keyring: any Keyring) {
        self.keyring = keyring
    }

    func load() throws -> JiraCredential? {
        guard let stored = try keyring.get(Self.name), let value = try? JSON.parse(stored), let token = value["token"]?.string
        else { return nil }
        return JiraCredential(email: value["email"]?.string, token: token)
    }

    func save(_ credential: JiraCredential) throws {
        let value: JSON = ["email": .string(credential.email), "token": .string(credential.token)]
        try keyring.set(Self.name, value.serialized())
    }

    func delete() throws {
        try keyring.delete(Self.name)
    }
}
