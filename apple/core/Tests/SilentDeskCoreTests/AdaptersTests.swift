// The shared adapters against the real file system and a real SQLCipher
// database, in a throwaway folder.
import Foundation
@testable import SilentDeskCore
import Testing
#if canImport(Glibc)
import Glibc
#elseif canImport(Darwin)
import Darwin
#endif

private func temporaryFolder() throws -> String {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("silentdesk-tests-\(UUID().uuidString)").path
    try FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: true)
    return folder
}

private func permissions(_ path: String) throws -> Int {
    try #require(FileManager.default.attributesOfItem(atPath: path)[.posixPermissions] as? Int)
}

// MARK: Hashing and addresses

private func hex(_ data: Data) -> String {
    data.map { String(format: "%02x", $0) }.joined()
}

@Test func sha256MatchesTheStandardVectors() {
    #expect(hex(Hashing.sha256(Data())) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    #expect(hex(Hashing.sha256(Data("abc".utf8))) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    let long = String(repeating: "a", count: 1_000)
    #expect(hex(Hashing.sha256(Data(long.utf8))) == "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3")
}

@Test func pkceChallengeIsTheURLSafeHashWithoutPadding() {
    // RFC 7636 appendix B.
    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    let challenge = Base64.encodeURLSafe(Hashing.sha256(Data(verifier.utf8)), padding: false)
    #expect(challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
}

@Test func loopbackHostsAreRecognized() {
    #expect(isLoopback("localhost"))
    #expect(isLoopback("127.0.0.1"))
    #expect(isLoopback("127.1.2.3"))
    #expect(isLoopback("::1"))
    #expect(!isLoopback("example.com"))
    #expect(!isLoopback("128.0.0.1"))
    #expect(!isLoopback(nil))
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
    let data = try #require(FileManager.default.contents(atPath: "\(folder)/nested/keyring.json"))
    #expect(try JSON.parse(data) == ["github-token": "ghp"], "one JSON object of strings, as the spec describes")
    #expect(String(decoding: data, as: UTF8.self).contains("\n"), "readable by a person")
}

#if canImport(Security)
import Security

@Test func theKeychainKeyringRoundTripsASecret() throws {
    // A build machine's login keychain can be locked. Without prompts the
    // call fails instead of waiting for a password, and the test steps
    // aside, recording a known issue so the log says it proved nothing.
    _ = SecKeychainSetUserInteractionAllowed(false)
    let keyring = KeychainKeyring(service: "com.silentdesk.tests")
    let name = "entry-\(UUID().uuidString)"
    defer { try? keyring.delete(name) }
    if let failure = caught(StorageError.self, { try keyring.set(name, "first") }) {
        let unavailable = [errSecInteractionNotAllowed, errSecNotAvailable].map { "(error \($0))" }
        guard unavailable.contains(where: failure.message.contains) else { throw failure }
        withKnownIssue("the login keychain is locked or missing on this machine") { throw failure }
        return
    }
    #expect(try keyring.get(name) == "first")
    try keyring.set(name, "second")
    #expect(try keyring.get(name) == "second", "set replaces the item")
    #expect(try keyring.get("never-\(name)") == nil)
    try keyring.delete(name)
    try keyring.delete(name)
    #expect(try keyring.get(name) == nil)
}
#endif

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

@Test func theLoopbackListenerFreesItsPortWhenStopped() async throws {
    let first = LoopbackListener(service: "slack", path: "/slack/callback", state: "s")
    try first.start(port: nil)
    let port = Int(try #require(URLComponents(string: first.redirectURI)?.port))
    // A client that connects and sends nothing would hold the handler until
    // its read times out; the pause lets the listener accept it first.
    let idle = connectToLoopback(port: port)
    defer { closeSocket(idle) }
    try await Task.sleep(for: .milliseconds(50))
    let began = ContinuousClock.now
    first.stop()
    #expect(ContinuousClock.now - began < .seconds(1), "stop returns as soon as the sockets are closed")
    // The port is free at once, as a sign-in retried right away needs.
    let second = LoopbackListener(service: "slack", path: "/slack/callback", state: "s")
    try second.start(port: port)
    second.stop()
    first.stop()
    LoopbackListener(service: "slack", path: "/", state: "s").stop()
}

private func connectToLoopback(port: Int) -> Int32 {
    #if canImport(Glibc)
    let descriptor = socket(AF_INET, Int32(SOCK_STREAM.rawValue), 0)
    #else
    let descriptor = socket(AF_INET, SOCK_STREAM, 0)
    #endif
    var address = sockaddr_in()
    address.sin_family = sa_family_t(AF_INET)
    address.sin_port = UInt16(port).bigEndian
    address.sin_addr = in_addr(s_addr: in_addr_t(0x7F00_0001).bigEndian)
    _ = withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    return descriptor
}

private func closeSocket(_ descriptor: Int32) {
    #if canImport(Glibc)
    _ = Glibc.close(descriptor)
    #else
    _ = Darwin.close(descriptor)
    #endif
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

// MARK: HTTPS policy

/// Answers every connection on a loopback port with the same canned response,
/// and records the request lines it received.
private final class CannedServer: @unchecked Sendable {
    let port: Int
    private let descriptor: Int32
    private let response: [UInt8]
    private let lock = NSLock()
    private var stopped = false
    private var received: [String] = []

    init(response: String) throws {
        #if canImport(Glibc)
        let listening = socket(AF_INET, Int32(SOCK_STREAM.rawValue), 0)
        #else
        let listening = socket(AF_INET, SOCK_STREAM, 0)
        #endif
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_addr = in_addr(s_addr: in_addr_t(0x7F00_0001).bigEndian)
        var size = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bound = withUnsafeMutablePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(listening, $0, size) == 0 && listen(listening, 4) == 0 && getsockname(listening, $0, &size) == 0
            }
        }
        try #require(bound, "the test server listens on a free loopback port")
        self.response = Array(response.utf8)
        descriptor = listening
        port = Int(UInt16(bigEndian: address.sin_port))
        Thread { [self] in self.serve() }.start()
    }

    /// The request line of each request, in order.
    var requests: [String] {
        lock.lock()
        defer { lock.unlock() }
        return received.map { $0.split(whereSeparator: \.isNewline).first.map(String.init) ?? "" }
    }

    /// The headers of each request, names in lowercase.
    var headers: [[String: String]] {
        lock.lock()
        defer { lock.unlock() }
        return received.map { text in
            var fields: [String: String] = [:]
            for line in text.split(whereSeparator: \.isNewline).dropFirst() {
                let parts = line.split(separator: ":", maxSplits: 1)
                guard parts.count == 2 else { continue }
                fields[parts[0].lowercased()] = parts[1].trimmingCharacters(in: .whitespaces)
            }
            return fields
        }
    }

    func stop() {
        lock.lock()
        stopped = true
        lock.unlock()
    }

    private func serve() {
        while true {
            var waiting = pollfd(fd: descriptor, events: Int16(POLLIN), revents: 0)
            let ready = poll(&waiting, 1, 100)
            lock.lock()
            let done = stopped
            lock.unlock()
            if done { break }
            guard ready > 0 else { continue }
            let client = accept(descriptor, nil, nil)
            guard client >= 0 else { continue }
            var buffer = [UInt8](repeating: 0, count: 8192)
            let count = recv(client, &buffer, buffer.count, 0)
            if count > 0 {
                lock.lock()
                received.append(String(decoding: buffer[0..<count], as: UTF8.self))
                lock.unlock()
            }
            #if canImport(Glibc)
            _ = response.withUnsafeBufferPointer { send(client, $0.baseAddress, $0.count, Int32(MSG_NOSIGNAL)) }
            #else
            _ = response.withUnsafeBufferPointer { send(client, $0.baseAddress, $0.count, 0) }
            #endif
            closeSocket(client)
        }
        closeSocket(descriptor)
    }
}

@Test func theHttpClientFollowsARedirectThePolicyAllows() async throws {
    let final = try CannedServer(response: "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    defer { final.stop() }
    let first = try CannedServer(response: "HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:\(final.port)/final\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    defer { first.stop() }
    let response = try await URLSessionHttp(allowLoopbackHTTP: true).request("GET", "http://127.0.0.1:\(first.port)/start")
    #expect(response.status == 200)
    #expect(String(decoding: response.body, as: UTF8.self) == "ok")
    #expect(final.requests == ["GET /final HTTP/1.1"])
}

@Test func theHttpClientDropsAuthorizationOnACrossOriginRedirect() async throws {
    let final = try CannedServer(response: "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    defer { final.stop() }
    let first = try CannedServer(response: "HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:\(final.port)/final\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    defer { first.stop() }
    let http = URLSessionHttp(allowLoopbackHTTP: true)
    let response = try await http.request("GET", "http://127.0.0.1:\(first.port)/start", headers: ["Authorization": "Bearer secret"])
    #expect(response.status == 200)
    #expect(first.headers.first?["authorization"] == "Bearer secret")
    // Another port is another origin, as a browser or httpx sees it.
    #expect(final.headers.first?["authorization"] == nil, "the token stays with the origin it was sent to")
}

@Test func theHttpClientRefusesARedirectAwayFromHttps() async throws {
    let server = try CannedServer(response: "HTTP/1.1 302 Found\r\nLocation: http://example.invalid/token\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    defer { server.stop() }
    let http = URLSessionHttp(allowLoopbackHTTP: true)
    let error = try #require(await caught(ConnectorError.self) { _ = try await http.request("GET", "http://127.0.0.1:\(server.port)/start") })
    #expect(error.kind == .network)
    #expect(error.message == "Only https addresses are allowed: http://example.invalid/token")
    #expect(server.requests == ["GET /start HTTP/1.1"], "the redirect was not followed")
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
    #expect(Base64.encodeURLSafe(Hashing.sha256(Data(verifier.utf8)), padding: false) == query["code_challenge"])
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
