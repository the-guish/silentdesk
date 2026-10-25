final class GitHubKeyringCredentials: GitHubCredentials {
    /// The keyring entry, as in legacy. See spec/storage.md.
    static let name = "github-token"

    private let keyring: any Keyring

    init(keyring: any Keyring) {
        self.keyring = keyring
    }

    func token() throws -> String? {
        try keyring.get(Self.name)
    }

    func saveToken(_ token: String) throws {
        try keyring.set(Self.name, token)
    }

    func deleteToken() throws {
        try keyring.delete(Self.name)
    }
}
