// The shared adapters against the real file system and a real SQLCipher
// database, in a throwaway folder.
import Foundation
@testable import SilentDeskCore
import Testing

private func temporaryFolder() throws -> String {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("silentdesk-tests-\(UUID().uuidString)").path
    try FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: true)
    return folder
}

private func permissions(_ path: String) throws -> Int {
    try #require(FileManager.default.attributesOfItem(atPath: path)[.posixPermissions] as? Int)
}

// MARK: Settings

@Test func settingsComeFromTheEnvironmentWithEmptyValuesUnset() {
    let settings = LocalSettings.fromEnvironment([
        "HOME": "/home/ana",
        "XDG_DATA_HOME": "/data/",
        "SILENTDESK_GOOGLE_CLIENT_ID": "",
        "SILENTDESK_SLACK_CLIENT_ID": "1.2",
        "SILENTDESK_SLACK_REDIRECT_PORT": "47699",
        "SILENTDESK_TEST_BASE_URL": "http://127.0.0.1:9/",
        "SILENTDESK_TEST_BROWSER": "follow",
        "SILENTDESK_TEST_NOW": "2026-10-24T12:00:00Z",
    ])
    #expect(settings.dataDirectory == "/data/silentdesk")
    #expect(settings.googleClientID == nil)
    #expect(settings.slackClientID == "1.2")
    #expect(settings.slackRedirectPort == 47699)
    #expect(settings.testBaseURL == "http://127.0.0.1:9")
    #expect(settings.testBrowser)
    #expect(settings.now == "2026-10-24T12:00:00Z")
    #expect(settings.baseURL("github", default: "https://api.github.com") == "http://127.0.0.1:9/github")
    #expect(LocalSettings(dataDirectory: "/d").baseURL("github", default: "https://api.github.com") == "https://api.github.com")
    #expect(LocalSettings.port(nil) == 47615)
    #expect(LocalSettings.port("0") == 47615)
    #expect(LocalSettings.port("70000") == 47615)
    #expect(LocalSettings.port("8x") == 47615)
    #expect(LocalSettings.port("8080") == 8080)
}

@Test func theDataFolderFollowsTheHome() {
    let folder = LocalSettings.dataDirectory(["HOME": "/home/ana"])
    #if os(macOS)
    #expect(folder == "/home/ana/Library/Application Support/SilentDesk")
    #else
    #expect(folder == "/home/ana/.local/share/silentdesk")
    #endif
}

// MARK: Keyring

@Test func fileKeyringKeepsEntriesInAPrivateFile() throws {
    let folder = try temporaryFolder()
    let keyring = FileKeyring(path: "\(folder)/nested/keyring.json")
    #expect(try keyring.get("database-key") == nil, "a missing file is an empty keyring")
    try keyring.set("database-key", "k1")
    try keyring.set("github-token", "ghp")
    #expect(try keyring.get("database-key") == "k1")
    #expect(try permissions("\(folder)/nested/keyring.json") == 0o600)
    try keyring.delete("database-key")
    try keyring.delete("never-there")
    #expect(try keyring.get("database-key") == nil)
    #expect(try keyring.get("github-token") == "ghp")
    let text = try String(contentsOfFile: "\(folder)/nested/keyring.json", encoding: .utf8)
    #expect(text == "{\n  \"github-token\": \"ghp\"\n}\n")
}

// MARK: Database

@Test func theDatabaseIsCreatedEncryptedAndMigrated() throws {
    let folder = try temporaryFolder()
    let keyring = FileKeyring(path: "\(folder)/keyring.json")
    let path = "\(folder)/data/silentdesk.db"
    let database = SqlcipherDatabase(path: path, keyring: keyring)
    let version = try database.transaction { db in try db.queryOne("PRAGMA user_version")?.first?.int }
    #expect(version == Int64(Migrations.all.count))
    let tables = try database.transaction { db in
        try db.query("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").compactMap { $0[0].string }
    }
    #expect(tables.contains("desk_topics") && tables.contains("gmail_messages") && tables.contains("slack_state"))
    #expect(try keyring.get("database-key")?.count == 64, "a 256-bit key as hex, generated on first run")
    #expect(try permissions("\(folder)/data") == 0o700)
    #expect(try permissions(path) == 0o600)
    let header = try #require(FileManager.default.contents(atPath: path)).prefix(16)
    #expect(String(decoding: header, as: UTF8.self) != "SQLite format 3\0", "the file is encrypted, not plain SQLite")

    // Another process with the same key reads what was written.
    try database.transaction { db in
        try db.execute("INSERT INTO desk_values (name, value) VALUES (?, ?)", [.text("last_synced"), .text("now")])
    }
    let again = SqlcipherDatabase(path: path, keyring: keyring)
    let value = try again.transaction { db in try db.queryOne("SELECT value FROM desk_values")?.first?.string }
    #expect(value == "now")
}

@Test func aTransactionThatThrowsIsRolledBack() throws {
    let folder = try temporaryFolder()
    let database = SqlcipherDatabase(path: "\(folder)/silentdesk.db", keyring: FileKeyring(path: "\(folder)/keyring.json"))
    #expect(throws: StorageError.self) {
        try database.transaction { db in
            try db.execute("INSERT INTO desk_values (name, value) VALUES ('a', 'b')")
            throw StorageError("stop")
        }
    }
    let count = try database.transaction { db in try db.queryOne("SELECT count(*) FROM desk_values")?.first?.int }
    #expect(count == 0)
}

@Test func aDatabaseWithoutItsKeyIsRefused() throws {
    let folder = try temporaryFolder()
    let path = "\(folder)/silentdesk.db"
    try "an existing database".write(toFile: path, atomically: true, encoding: .utf8)
    let database = SqlcipherDatabase(path: path, keyring: FileKeyring(path: "\(folder)/keyring.json"))
    let error = try #require(caught(StorageError.self) { try database.transaction { _ in } })
    #expect(error.message.contains("key is missing"))
}

@Test func aDatabaseWithTheWrongKeyIsRefused() throws {
    let folder = try temporaryFolder()
    let path = "\(folder)/silentdesk.db"
    _ = try SqlcipherDatabase(path: path, keyring: FileKeyring(path: "\(folder)/first.json")).transaction { _ in }
    let other = FileKeyring(path: "\(folder)/second.json")
    try other.set(SqlcipherDatabase.keyName, String(repeating: "ab", count: 32))
    #expect(throws: StorageError.self) {
        try SqlcipherDatabase(path: path, keyring: other).transaction { _ in }
    }
}

// MARK: Loopback

@Test func theLoopbackListenerReadsTheRedirect() {
    let listener = LoopbackListener(service: "gmail", path: "/", state: "s1")
    #expect(listener.outcome(of: "GET /?code=c1&state=s1 HTTP/1.1") == .success("c1"))
    #expect(listener.outcome(of: "GET /?state=s1&code=c1&code=c2 HTTP/1.1") == .success("c1"), "the first value wins")
    #expect(listener.outcome(of: "GET /favicon.ico HTTP/1.1") == nil)
    #expect(listener.outcome(of: "GET / HTTP/1.1") == nil, "no code and no error is not the redirect")
    #expect(listener.outcome(of: "POST /?code=c1&state=s1 HTTP/1.1") == nil)
    #expect(listener.outcome(of: "") == nil)
    #expect(listener.outcome(of: "GET /?code=c1&state=other HTTP/1.1") == .failure(.auth("gmail", "The sign-in response did not match this request.")))
    #expect(listener.outcome(of: "GET /?error=access_denied&state=s1 HTTP/1.1") == .failure(.auth("gmail", "Access was denied.")))
    #expect(listener.outcome(of: "GET /?error=server_error&state=s1 HTTP/1.1") == .failure(.auth("gmail", "Sign-in failed: server_error.")))
    let slack = LoopbackListener(service: "slack", path: "/slack/callback", state: "s1")
    #expect(slack.outcome(of: "GET /slack/callback?code=c&state=s1 HTTP/1.1") == .success("c"))
    #expect(slack.outcome(of: "GET /?code=c&state=s1 HTTP/1.1") == nil)
}

@Test func theLoopbackListenerServesABrowser() async throws {
    let listener = LoopbackListener(service: "gmail", path: "/", state: "s1")
    try listener.start(port: nil)
    defer { listener.stop() }
    #expect(listener.redirectURI.hasPrefix("http://127.0.0.1:"))
    let http = URLSessionHttp(allowLoopbackHTTP: true)
    let notFound = try await http.request("GET", listener.redirectURI + "/favicon.ico")
    #expect(notFound.status == 404)
    let page = try await http.request("GET", listener.redirectURI + "?code=c1&state=s1")
    #expect(page.status == 200)
    #expect(String(decoding: page.body, as: UTF8.self).contains("Sign-in received"))
    #expect(try await listener.code(timeout: .seconds(5)) == "c1")
    let late = try await http.request("GET", listener.redirectURI + "?code=c2&state=s1")
    #expect(late.status == 404, "the outcome is delivered once")
}

@Test func theLoopbackListenerRefusesABusyPort() throws {
    let first = LoopbackListener(service: "slack", path: "/slack/callback", state: "s")
    try first.start(port: nil)
    defer { first.stop() }
    let port = Int(try #require(URLComponents(string: first.redirectURI)?.port))
    let second = LoopbackListener(service: "slack", path: "/slack/callback", state: "s")
    let error = try #require(caught(ConnectorError.self) { try second.start(port: port) })
    #expect(error.kind == .auth)
    #expect(error.message.contains("\(port)"))
}

// MARK: OAuth

/// Answers every token request with the same body, and records the requests.
private final class FakeHttp: Http, @unchecked Sendable {
    let lock = NSLock()
    var requests: [(method: String, url: String, form: [(String, String)]?)] = []
    let tokens: JSON
    let status: Int

    init(tokens: JSON, status: Int = 200) {
        self.tokens = tokens
        self.status = status
    }

    func request(_ method: String, _ url: String, headers: [String: String], params: [(String, String)], json: JSON?, form: [(String, String)]?) async throws -> Response {
        record(method, url, form)
        return Response(status: status, headers: [:], body: tokens.data)
    }

    private func record(_ method: String, _ url: String, _ form: [(String, String)]?) {
        lock.lock()
        defer { lock.unlock() }
        requests.append((method, url, form))
    }
}

/// Signs in at once: it requests the redirect the provider would send.
private final class SigningInBrowser: Browser {
    let opened = Outcome<String>()

    func open(_ url: String) async throws {
        opened.resolve(.success(url))
        let query = Dictionary(URLQuery.parse(URLComponents(string: url)?.percentEncodedQuery ?? ""), uniquingKeysWith: { first, _ in first })
        let redirect = try #require(query["redirect_uri"]) + "?code=the-code&state=" + (query["state"] ?? "")
        _ = try await URLSessionHttp(allowLoopbackHTTP: true).request("GET", redirect)
    }
}

@Test func oauthSignsInWithPKCEAndExchangesTheCode() async throws {
    let http = FakeHttp(tokens: ["access_token": "a1", "refresh_token": "r1", "scope": "x y"])
    let browser = SigningInBrowser()
    let oauth = LoopbackOAuth(http: http, browser: browser, timeout: .seconds(5))
    let client = OAuthClient(
        service: "gmail", authorizeURL: "https://accounts.example/auth", tokenURL: "https://oauth.example/token",
        clientID: "cid", clientSecret: "secret", extra: [("access_type", "offline")])
    let tokens = try await oauth.signIn(client, scopes: ["x", "y"])
    #expect(tokens.accessToken == "a1" && tokens.refreshToken == "r1" && tokens.scopes == ["x", "y"])

    let opened = try await browser.opened.value(timeout: .seconds(1)) { StorageError("never opened") }
    let query = Dictionary(URLQuery.parse(URLComponents(string: opened)?.percentEncodedQuery ?? ""), uniquingKeysWith: { first, _ in first })
    #expect(opened.hasPrefix("https://accounts.example/auth?"))
    #expect(query["client_id"] == "cid" && query["response_type"] == "code" && query["scope"] == "x y")
    #expect(query["code_challenge_method"] == "S256" && query["access_type"] == "offline")

    let exchange = try #require(http.requests.first)
    #expect(exchange.method == "POST" && exchange.url == "https://oauth.example/token")
    let form = Dictionary(try #require(exchange.form), uniquingKeysWith: { first, _ in first })
    #expect(form["grant_type"] == "authorization_code" && form["code"] == "the-code")
    #expect(form["client_id"] == "cid" && form["client_secret"] == "secret")
    #expect(form["redirect_uri"] == query["redirect_uri"])
    let verifier = try #require(form["code_verifier"])
    #expect(Base64.encodeURLSafe(SHA256.hash(Data(verifier.utf8)), padding: false) == query["code_challenge"])
}

@Test func oauthReportsRevokedGrantsAsAuthErrors() async throws {
    let http = FakeHttp(tokens: ["error": "invalid_grant"], status: 400)
    let oauth = LoopbackOAuth(http: http, browser: SigningInBrowser())
    let client = OAuthClient(service: "tasks", authorizeURL: "https://a", tokenURL: "https://t", clientID: "cid")
    let error = try #require(await caught(ConnectorError.self) { _ = try await oauth.refresh(client, refreshToken: "dead") })
    #expect(error.kind == .auth)
    #expect(http.requests.first?.form?.contains { $0 == ("refresh_token", "dead") } == true)
    await oauth.revoke(url: "https://t/revoke", token: "r")
    #expect(http.requests.last?.form?.first.map { $0 == ("token", "r") } == true)
}
