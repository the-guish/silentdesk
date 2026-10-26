/// The few Gmail API calls SilentDesk makes, ported from the legacy backend.
/// Reads ask for headers only; bodies are never fetched.

import Foundation

actor GmailHTTPAPI: GmailAPI {
    /// Google allows 15,000 quota units per user per minute, and reading one
    /// message costs 5: 50 a second. Staying at 40 leaves room for other calls.
    static let readPace: Duration = .milliseconds(25)
    static let maxInFlight = 20
    /// Waits after a rate-limit or server error: 1, 2, 4, 8, 16 and 32 seconds,
    /// over a minute in all, as Google counts quota per minute.
    static let retries = 6
    /// The reasons a 403 gives when a per-minute quota runs out.
    static let rateLimits = ["rateLimitExceeded", "userRateLimitExceeded"]

    typealias Sleep = @Sendable (Duration) async throws -> Void

    private let http: any Http
    private let base: String
    /// Waits between retries; tests pass one that does not wait.
    private let sleep: Sleep
    /// After a rate-limit, every call waits until then, not only the one that
    /// hit it: the quota is per user.
    private var pausedUntil: ContinuousClock.Instant?
    private let service = GmailRules.service

    init(http: any Http, baseURL: String, sleep: @escaping Sleep = { try await Task.sleep(for: $0) }) {
        self.http = http
        base = "\(baseURL)/gmail/v1/users/me"
        self.sleep = sleep
    }

    /// Gmail IDs are hex strings; anything else is kept out of URLs.
    static func isGmailID(_ value: String) -> Bool {
        !value.isEmpty && value.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber) }
    }

    /// Sends the request, again after rate-limit and server errors.
    private func call(_ method: String, _ path: String, token: String, params: [(String, String)] = [], json: JSON? = nil)
        async throws -> JSON
    {
        for attempt in 0...Self.retries {
            if let pausedUntil, pausedUntil > .now {
                try await sleep(ContinuousClock.now.duration(to: pausedUntil))
            }
            let response = try await http.request(
                method, "\(base)/\(path)", headers: ["Authorization": "Bearer \(token)"], params: params, json: json)
            let body: JSON? = response.body.isEmpty ? .object([:]) : try? JSON.parse(response.body)
            if response.isSuccess {
                guard let body, body.object != nil else {
                    throw ConnectorError.network(service, "Gmail's answer could not be read.")
                }
                return body
            }
            let error = body?["error"]?.object != nil ? body?["error"] : nil
            let message = error?["message"]?.string ?? ""
            let reasons = error?["errors"]?.array?.compactMap { $0["reason"]?.string } ?? []
            let lowered = message.lowercased()
            let transient = [429, 500, 502, 503, 504].contains(response.status)
                || (response.status == 403
                    && (reasons.contains(where: Self.rateLimits.contains) || lowered.contains("rate limit")
                        || lowered.contains("per minute")))
            if transient && attempt < Self.retries {
                let resume = ContinuousClock.now + .seconds(1 << attempt)
                pausedUntil = pausedUntil.map { max($0, resume) } ?? resume
                continue
            }
            if response.status == 401 {
                throw ConnectorError.auth(service, "Google rejected the access token.")
            }
            if response.status == 403 && message.contains("insufficient authentication scopes") {
                throw ConnectorError.auth(service, "Gmail did not grant this. Disconnect Gmail and connect it again.")
            }
            throw ConnectorError.remote(
                service, "Gmail answered \(response.status): \(message.isEmpty ? "no details" : message).",
                status: response.status)
        }
        throw ConnectorError.network(service, "Gmail kept failing.")
    }

    func profile(token: String) async throws -> GmailProfile {
        let body = try await call("GET", "profile", token: token)
        guard let email = body["emailAddress"]?.string, let historyID = body["historyId"]?.string else {
            throw ConnectorError.network(service, "Gmail's profile could not be read.")
        }
        return GmailProfile(email: email, historyID: historyID)
    }

    func inboxIDs(token: String) async throws -> [String] {
        var ids: [String] = []
        var page: String?
        while true {
            var params = [("labelIds", "INBOX"), ("maxResults", "500")]
            if let page { params.append(("pageToken", page)) }
            let body = try await call("GET", "messages", token: token, params: params)
            ids += body["messages"]?.array?.compactMap { $0["id"]?.string } ?? []
            page = body["nextPageToken"]?.string
            if page == nil {
                return ids
            }
        }
    }

    func inboxChanges(token: String, since historyID: String) async throws -> (ids: [String], historyID: String)? {
        var added: [String] = []
        var page: String?
        while true {
            var params = [
                ("startHistoryId", historyID), ("labelId", "INBOX"), ("historyTypes", "messageAdded"),
                ("historyTypes", "labelAdded"),
            ]
            if let page { params.append(("pageToken", page)) }
            let body: JSON
            do {
                body = try await call("GET", "history", token: token, params: params)
            } catch let error as ConnectorError where error.kind == .remote && error.status == 404 {
                return nil
            }
            for record in body["history"]?.array ?? [] {
                let changes = (record["messagesAdded"]?.array ?? []) + (record["labelsAdded"]?.array ?? [])
                for change in changes {
                    let message = change["message"]
                    let labels = message?["labelIds"]?.array?.compactMap(\.string) ?? []
                    if labels.contains("INBOX"), let id = message?["id"]?.string {
                        added.append(id)
                    }
                }
            }
            page = body["nextPageToken"]?.string
            if page == nil {
                let next: String
                switch body["historyId"] {
                case .string(let value)?: next = value
                case .int(let value)?: next = String(value)
                default: next = historyID
                }
                return (added, next)
            }
        }
    }

    private func metadata(token: String, messageID: String, headers: [String]) async throws -> JSON? {
        guard Self.isGmailID(messageID) else { return nil }
        do {
            return try await call(
                "GET", "messages/\(messageID)", token: token,
                params: [("format", "metadata")] + headers.map { ("metadataHeaders", $0) })
        } catch let error as ConnectorError where error.kind == .remote && error.status == 404 {
            return nil
        }
    }

    private func read(token: String, messageID: String) async throws -> GmailMessage? {
        guard let raw = try await metadata(token: token, messageID: messageID, headers: ["Subject", "From"]) else {
            return nil
        }
        let labels = raw["labelIds"]?.array?.compactMap(\.string) ?? []
        guard !labels.contains("DRAFT"), !labels.contains("CHAT"), let date = Self.date(raw["internalDate"]) else {
            return nil
        }
        let id = raw["id"]?.string ?? messageID
        return GmailMessage(
            messageID: id,
            threadID: raw["threadId"]?.string ?? id,
            direction: Self.direction(raw),
            sender: Self.header(raw, "From"),
            subject: Self.header(raw, "Subject"),
            date: date)
    }

    func messages(token: String, ids: [String], progress: @escaping @Sendable (Int) -> Void) async throws -> [GmailMessage] {
        var found: [Int: GmailMessage] = [:]
        // Reads finish in any order; the messages come back in the order of `ids`.
        try await withThrowingTaskGroup(of: (Int, GmailMessage?).self) { group in
            var pending = ids.enumerated().makeIterator()
            var pace = Pace(period: Self.readPace)
            var inFlight = 0
            var done = 0
            while true {
                while inFlight < Self.maxInFlight, let (position, messageID) = pending.next() {
                    try await pace.tick()
                    group.addTask { (position, try await self.read(token: token, messageID: messageID)) }
                    inFlight += 1
                }
                guard inFlight > 0, let (position, message) = try await group.next() else { break }
                inFlight -= 1
                if let message {
                    found[position] = message
                }
                done += 1
                progress(done)
            }
        }
        return found.keys.sorted().map { found[$0]! }
    }

    func original(token: String, messageID: String) async throws -> GmailOriginal {
        let headers = ["From", "To", "Reply-To", "Subject", "Message-ID", "References"]
        guard let raw = try await metadata(token: token, messageID: messageID, headers: headers) else {
            throw ConnectorError.remote(service, "That email is no longer in Gmail.", status: 404)
        }
        return GmailOriginal(
            direction: Self.direction(raw),
            sender: Self.header(raw, "From"),
            to: Self.header(raw, "To"),
            replyTo: Self.header(raw, "Reply-To"),
            subject: Self.header(raw, "Subject"),
            headerID: Self.header(raw, "Message-ID"),
            references: Self.header(raw, "References"))
    }

    func send(token: String, threadID: String, message: String) async throws {
        let raw = Base64.encodeURLSafe(Data(message.utf8), padding: true)
        _ = try await call("POST", "messages/send", token: token, json: ["raw": .string(raw), "threadId": .string(threadID)])
    }

    func trashThread(token: String, threadID: String) async throws {
        guard Self.isGmailID(threadID) else {
            throw ConnectorError.remote(service, "That thread is not a Gmail thread.", status: 404)
        }
        do {
            _ = try await call("POST", "threads/\(threadID)/trash", token: token)
        } catch let error as ConnectorError where error.kind == .remote && error.status == 404 {
            // A thread that no longer exists counts as trashed.
        }
    }

    func trashMessage(token: String, messageID: String) async throws {
        guard Self.isGmailID(messageID) else {
            throw ConnectorError.remote(service, "That message is not a Gmail message.", status: 404)
        }
        do {
            _ = try await call("POST", "messages/\(messageID)/trash", token: token)
        } catch let error as ConnectorError where error.kind == .remote && error.status == 404 {
            // A message that no longer exists counts as trashed.
        }
    }

    /// Gmail's internal date, milliseconds since the epoch, in RFC 3339.
    static func date(_ millis: JSON?) -> String? {
        guard let text = millis?.string, !text.isEmpty, text.allSatisfy(\.isNumber), let value = Int64(text) else {
            return nil
        }
        return RFC3339.format(milliseconds: value)
    }

    static func header(_ message: JSON, _ name: String) -> String {
        for header in message["payload"]?["headers"]?.array ?? [] {
            if (header["name"]?.string ?? "").lowercased() == name.lowercased() {
                return (header["value"]?.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return ""
    }

    static func direction(_ message: JSON) -> Direction {
        (message["labelIds"]?.array?.compactMap(\.string) ?? []).contains("SENT") ? .outbound : .inbound
    }

    /// Lets one call through every `period`; a late call delays the next ones
    /// rather than letting them burst.
    private struct Pace {
        let period: Duration
        var next: ContinuousClock.Instant?

        init(period: Duration) {
            self.period = period
        }

        mutating func tick() async throws {
            let now = ContinuousClock.now
            guard let next, now < next else {
                self.next = now + period
                return
            }
            try await Task.sleep(until: next, clock: .continuous)
            self.next = next + period
        }
    }
}
