/// The most recent direct messages, sent and received, in 1:1 and group DMs:
/// one topic per conversation. Read-only.

import Foundation

final class SlackConnector: Connector {
    private let api: any SlackAPI
    private let authorization: any SlackAuthorization
    private let credentials: any SlackCredentials
    private let state: any SlackStateStore

    init(api: any SlackAPI, authorization: any SlackAuthorization, credentials: any SlackCredentials, state: any SlackStateStore) {
        self.api = api
        self.authorization = authorization
        self.credentials = credentials
        self.state = state
    }

    var service: String { SlackRules.service }

    private var now: Int { Int(Date().timeIntervalSince1970) }

    func status() async throws -> ServiceStatus {
        let account = try await state.load()
        let connected = try account != nil && credentials.load() != nil
        let label = connected ? account.map { "\($0.userName) · \($0.teamName)" } : nil
        return ServiceStatus(service: service, configured: authorization.configured, connected: connected, account: label)
    }

    /// Signs in through the browser, then keeps the token. An older token is revoked.
    func connect(_ params: [String: String]) async throws -> ServiceStatus {
        let credential = try await authorization.signIn()
        let account = try await api.identity(token: credential.accessToken)
        if let old = try credentials.load(), old.accessToken != credential.accessToken {
            await authorization.revoke(accessToken: old.accessToken)
        }
        try credentials.save(credential)
        try await state.save(account)
        return try await status()
    }

    /// Revokes the token at Slack, renewing it first if it had expired, then
    /// forgets it and the account.
    func disconnect() async throws -> ServiceStatus {
        if var credential = try credentials.load() {
            if SlackRules.needsRefresh(credential, now: now), authorization.configured {
                if let renewed = try? await authorization.refresh(credential) {
                    credential = renewed
                }
            }
            await authorization.revoke(accessToken: credential.accessToken)
        }
        try credentials.delete()
        try await state.clear()
        return try await status()
    }

    private func credential() async throws -> (SlackCredential, SlackAccount) {
        guard var credential = try credentials.load(), let account = try await state.load() else {
            throw ConnectorError.auth(service, "Slack is not connected.")
        }
        if SlackRules.needsRefresh(credential, now: now) {
            do {
                credential = try await authorization.refresh(credential)
            } catch let error as ConnectorError where error.kind == .auth {
                try credentials.delete()
                throw ConnectorError.auth(service, "\(error.message) Connect Slack again.")
            }
            try credentials.save(credential)
        }
        return (credential, account)
    }

    func sync() async throws -> SyncResult {
        let (credential, account) = try await credential()
        let token = credential.accessToken
        let page = min(SlackRules.syncCount * 3, 100)
        var messages: [SlackDirectMessage] = []
        do {
            var found: [SlackMatch] = []
            for query in SlackRules.queries(me: account.userID) {
                found += try await api.search(token: token, query: query, count: page)
            }
            var names: [String: String] = [:]
            for match in SlackRules.selectRecent(found, count: SlackRules.syncCount) {
                messages.append(try await message(token: token, me: account.userID, match: match, names: &names))
            }
        } catch let error as ConnectorError where error.kind == .auth {
            // Revoked or expired: forget the token, keep the topics.
            try credentials.delete()
            throw ConnectorError.auth(service, "\(error.message) Connect Slack again.")
        }
        return SyncResult(topics: SlackRules.topics(messages), removed: [], complete: true)
    }

    /// A user's name, read once per sync.
    private func name(token: String, userID: String, names: inout [String: String]) async throws -> String {
        if let known = names[userID] {
            return known
        }
        let found = try await api.userName(token: token, userID: userID)
        let name = found.isEmpty ? "someone" : found
        names[userID] = name
        return name
    }

    private func message(token: String, me: String, match: SlackMatch, names: inout [String: String]) async throws
        -> SlackDirectMessage
    {
        let outbound = match.user == me
        let author: String
        if let user = match.user {
            author = try await name(token: token, userID: user, names: &names)
        } else {
            author = match.username?.isEmpty == false ? match.username! : "someone"
        }
        let counterpart: String
        if !match.isIM {
            counterpart = "Group DM"
        } else if outbound {
            counterpart = try await name(token: token, userID: match.channelName, names: &names)
        } else {
            counterpart = author
        }
        var mentioned: [String: String] = [:]
        for userID in SlackRules.mentionIDs(match.text) {
            mentioned[userID] = try await name(token: token, userID: userID, names: &names)
        }
        return SlackDirectMessage(
            channelID: match.channelID,
            ts: match.ts,
            direction: outbound ? .outbound : .inbound,
            author: author,
            counterpart: counterpart,
            preview: SlackRules.preview(SlackRules.plainText(match.text, names: mentioned)),
            permalink: match.permalink,
            date: SlackRules.rfc3339(ts: match.ts))
    }

    /// The conversation's recent messages, read live, oldest first. Join and
    /// leave events are left out. Nothing is stored.
    func history(topicKey: String) async throws -> [Message] {
        let (credential, account) = try await credential()
        let token = credential.accessToken
        var names: [String: String] = [:]
        var messages: [Message] = []
        do {
            let entries = try await api.history(token: token, channelID: topicKey, count: SlackRules.historyCount)
            for entry in entries.sorted(by: { SlackRules.tsValue($0.ts) < SlackRules.tsValue($1.ts) }) {
                if let subtype = entry.subtype, SlackRules.eventSubtypes.contains(subtype) {
                    continue
                }
                let author: String
                if let user = entry.user {
                    author = try await name(token: token, userID: user, names: &names)
                } else {
                    author = entry.username?.isEmpty == false ? entry.username! : "someone"
                }
                var mentioned: [String: String] = [:]
                for userID in SlackRules.mentionIDs(entry.text) {
                    mentioned[userID] = try await name(token: token, userID: userID, names: &names)
                }
                messages.append(
                    Message(
                        key: entry.ts,
                        direction: entry.user == account.userID ? .outbound : .inbound,
                        author: author,
                        text: SlackRules.plainText(entry.text, names: mentioned).trimmingCharacters(in: .whitespacesAndNewlines),
                        date: SlackRules.rfc3339(ts: entry.ts)))
            }
        } catch let error as ConnectorError where error.kind == .auth {
            try credentials.delete()
            throw ConnectorError.auth(service, "\(error.message) Connect Slack again.")
        }
        return messages
    }

    func reply(topicKey: String, body: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk has read-only access to Slack.")
    }

    func deleteTopic(topicKey: String) async throws {
        throw ConnectorError.unsupported(service, "SilentDesk has read-only access to Slack.")
    }

    func deleteItem(topicKey: String, itemKey: String) async throws -> Topic? {
        throw ConnectorError.unsupported(service, "SilentDesk has read-only access to Slack.")
    }
}
