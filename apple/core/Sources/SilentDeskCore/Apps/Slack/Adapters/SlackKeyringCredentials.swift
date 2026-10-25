final class SlackKeyringCredentials: SlackCredentials {
    /// The keyring entry, as in legacy: {"access_token", "refresh_token", "expires_at"}.
    static let name = "slack-credential"

    private let keyring: any Keyring

    init(keyring: any Keyring) {
        self.keyring = keyring
    }

    func load() throws -> SlackCredential? {
        guard let stored = try keyring.get(Self.name), let value = try? JSON.parse(stored),
            let access = value["access_token"]?.string
        else { return nil }
        return SlackCredential(
            accessToken: access, refreshToken: value["refresh_token"]?.string, expiresAt: value["expires_at"]?.int)
    }

    func save(_ credential: SlackCredential) throws {
        let value: JSON = [
            "access_token": .string(credential.accessToken),
            "refresh_token": .string(credential.refreshToken),
            "expires_at": .int(credential.expiresAt),
        ]
        try keyring.set(Self.name, value.serialized())
    }

    func delete() throws {
        try keyring.delete(Self.name)
    }
}
