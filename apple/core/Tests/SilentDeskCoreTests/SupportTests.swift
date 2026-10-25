import Foundation
@testable import SilentDeskCore
import Testing

private func hex(_ data: Data) -> String {
    data.map { String(format: "%02x", $0) }.joined()
}

@Test func sha256MatchesTheStandardVectors() {
    #expect(hex(SHA256.hash(Data())) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    #expect(hex(SHA256.hash(Data("abc".utf8))) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    let long = String(repeating: "a", count: 1_000)
    #expect(hex(SHA256.hash(Data(long.utf8))) == "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3")
}

@Test func pkceChallengeIsTheURLSafeHashWithoutPadding() {
    // RFC 7636 appendix B.
    let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    let challenge = Base64.encodeURLSafe(SHA256.hash(Data(verifier.utf8)), padding: false)
    #expect(challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
}

@Test func base64KeepsPaddingWhenAsked() {
    #expect(Base64.encodeURLSafe(Data([0xFB, 0xFF]), padding: true) == "-_8=")
    #expect(Base64.encodeURLSafe(Data([0xFB, 0xFF]), padding: false) == "-_8")
    #expect(Base64.encode(Data("hi".utf8)) == "aGk=")
}

@Test func rfc3339FormatsSecondsAndMilliseconds() {
    #expect(RFC3339.format(seconds: 0) == "1970-01-01T00:00:00Z")
    #expect(RFC3339.format(seconds: 1_761_300_000) == "2025-10-24T10:00:00Z")
    #expect(RFC3339.format(milliseconds: 1_761_300_000_000) == "2025-10-24T10:00:00Z")
    #expect(RFC3339.format(milliseconds: 1_761_300_000_120) == "2025-10-24T10:00:00.12Z")
    #expect(RFC3339.format(milliseconds: 1_761_300_000_007) == "2025-10-24T10:00:00.007Z")
    #expect(RFC3339.format(seconds: -1) == "1969-12-31T23:59:59Z")
    #expect(RFC3339.format(seconds: 951_782_400) == "2000-02-29T00:00:00Z")
}

@Test func rfc3339ReadsISO8601WithOffsets() {
    #expect(RFC3339.fromISO8601("2026-10-23T10:00:00.000+0200") == "2026-10-23T08:00:00Z")
    #expect(RFC3339.fromISO8601("2026-10-24T09:30:00.000+0000") == "2026-10-24T09:30:00Z")
    #expect(RFC3339.fromISO8601("2026-10-24T23:30:00-01:30") == "2026-10-25T01:00:00Z")
    #expect(RFC3339.fromISO8601("2026-10-24T09:30:00Z") == "2026-10-24T09:30:00Z")
    #expect(RFC3339.fromISO8601("2026-10-24T09:30Z") == "2026-10-24T09:30:00Z")
    #expect(RFC3339.fromISO8601("2026-10-24T09:30:00") == nil, "no offset")
    #expect(RFC3339.fromISO8601("2026-10-24") == nil)
    #expect(RFC3339.fromISO8601("yesterday") == nil)
    #expect(RFC3339.fromISO8601("") == nil)
}

@Test func civilDatesRoundTrip() {
    for days in stride(from: Int64(-800_000), through: 800_000, by: 997) {
        let (year, month, day) = RFC3339.civil(fromDays: days)
        #expect(RFC3339.days(fromCivil: year, month, day) == days)
    }
}

@Test func queryEncodingRoundTrips() {
    let pairs = [("q", "is:pr is:open author:@me"), ("sort", "updated"), ("scope", "a+b/c&d=e"), ("empty", "")]
    let encoded = URLQuery.encode(pairs)
    #expect(encoded == "q=is%3Apr%20is%3Aopen%20author%3A%40me&sort=updated&scope=a%2Bb%2Fc%26d%3De&empty=")
    #expect(URLQuery.parse(encoded).map { "\($0)=\($1)" } == pairs.map { "\($0)=\($1)" })
    #expect(URLQuery.parse("a=1+2&b").map { "\($0)=\($1)" } == ["a=1 2", "b="])
    #expect(URLQuery.append([("a", "1")], to: "https://x/y") == "https://x/y?a=1")
    #expect(URLQuery.append([("a", "1")], to: "https://x/y?b=2") == "https://x/y?b=2&a=1")
    #expect(URLQuery.append([], to: "https://x/y") == "https://x/y")
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

@Test func asyncMutexSerializesHolders() async {
    let mutex = AsyncMutex()
    let log = Log()
    await withTaskGroup(of: Void.self) { group in
        for index in 0..<5 {
            group.addTask {
                await mutex.withLock {
                    await log.append("start \(index)")
                    try? await Task.sleep(for: .milliseconds(5))
                    await log.append("end \(index)")
                }
            }
        }
    }
    let entries = await log.entries
    for pair in stride(from: 0, to: entries.count, by: 2) {
        #expect(entries[pair].hasPrefix("start"), "a holder never starts while another holds the lock")
        #expect(entries[pair + 1].hasPrefix("end"))
        #expect(entries[pair].dropFirst(6) == entries[pair + 1].dropFirst(4))
    }
}

private actor Log {
    var entries: [String] = []
    func append(_ entry: String) { entries.append(entry) }
}

@Test func outcomeDeliversOnceOrTimesOut() async throws {
    let outcome = Outcome<String>()
    outcome.resolve(.success("first"))
    outcome.resolve(.success("second"))
    #expect(try await outcome.value(timeout: .seconds(1), timedOut: { StorageError("late") }) == "first")

    let waiting = Outcome<String>()
    await #expect(throws: StorageError.self) {
        try await waiting.value(timeout: .milliseconds(20), timedOut: { StorageError("late") })
    }
}
