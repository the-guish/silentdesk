final class GmailKeyringCredentials: GmailCredentials {
    /// The keyring entry, as in legacy.
    static let name = "gmail-refresh-token"

    private let keyring: any Keyring

    init(keyring: any Keyring) {
        self.keyring = keyring
    }

    func refreshToken() throws -> String? {
        try keyring.get(Self.name)
    }

    func saveRefreshToken(_ token: String) throws {
        try keyring.set(Self.name, token)
    }

    func deleteRefreshToken() throws {
        try keyring.delete(Self.name)
    }
}
