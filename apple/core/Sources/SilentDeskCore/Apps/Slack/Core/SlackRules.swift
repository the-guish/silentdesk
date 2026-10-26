/// Rules about Slack: which messages, their text, and their topics. See
/// legacy/docs/specs/integrations/slack.md.

import Foundation

enum SlackRules {
    static let service = "slack"
    /// search:read finds recent direct messages; users:read turns user IDs into
    /// names; the history scopes show a conversation. Nothing is written to Slack.
    static let userScopes = ["search:read", "users:read", "im:history", "mpim:history"]
    /// How many recent direct messages a sync keeps.
    static let syncCount = 10
    /// Longest topic title taken from a message, in characters.
    static let previewCharacters = 120
    /// Refresh a little before the access token expires, in seconds.
    static let expiryMargin = 60
    /// How many recent messages the topic screen shows.
    static let historyCount = 50
    /// Subtypes that are events, not messages someone wrote.
    static let eventSubtypes: Set<String> = ["channel_join", "channel_leave", "group_join", "group_leave"]

    /// Searches that together find direct messages sent to and by the user.
    /// Results are filtered to direct conversations afterwards.
    static func queries(me: String) -> [String] {
        ["to:me", "from:<@\(me)>"]
    }

    static func needsRefresh(_ credential: SlackCredential, now: Int) -> Bool {
        guard credential.refreshToken != nil, let expiresAt = credential.expiresAt else { return false }
        return now >= expiresAt - expiryMargin
    }

    static func tsValue(_ ts: String) -> Double {
        Double(ts) ?? 0
    }

    static func rfc3339(ts: String) -> String {
        RFC3339.format(seconds: Int64(tsValue(ts).rounded(.towardZero)))
    }

    /// Direct messages only (1:1 and group), without repeats, newest first.
    static func selectRecent(_ matches: [SlackMatch], count: Int) -> [SlackMatch] {
        var seen = Set<String>()
        var kept: [SlackMatch] = []
        for match in matches where match.isIM || match.isMPIM {
            let identity = "\(match.channelID)\u{0}\(match.ts)"
            if seen.insert(identity).inserted {
                kept.append(match)
            }
        }
        return Array(kept.sorted { tsValue($0.ts) > tsValue($1.ts) }.prefix(count))
    }

    /// User IDs mentioned as <@U123> or <@U123|name>.
    static func mentionIDs(_ text: String) -> [String] {
        let parts = text.components(separatedBy: "<@").dropFirst()
        let ids = parts.map { rest -> String in
            String(rest.prefix { $0 != ">" && $0 != "|" })
        }
        return Set(ids).sorted()
    }

    /// Slack's markup as plain text: <@U1> becomes @Name, <#C1|general>
    /// #general, <https://x|label> label, <!here> @here, and HTML entities
    /// their characters.
    static func plainText(_ text: String, names: [String: String]) -> String {
        func nonEmpty(_ value: String?) -> String? {
            value?.isEmpty == false ? value : nil
        }
        var out = ""
        var rest = Substring(text)
        while let start = rest.firstIndex(of: "<") {
            out += rest[..<start]
            let after = rest[rest.index(after: start)...]
            guard let end = after.firstIndex(of: ">") else {
                out += rest[start...]
                rest = ""
                break
            }
            let token = after[..<end]
            let target: Substring
            let label: String?
            if let bar = token.firstIndex(of: "|") {
                target = token[..<bar]
                label = String(token[token.index(after: bar)...])
            } else {
                target = token
                label = nil
            }
            if target.hasPrefix("@") {
                out += "@" + (nonEmpty(names[String(target.dropFirst())]) ?? nonEmpty(label) ?? "someone")
            } else if target.hasPrefix("#") {
                out += "#" + (nonEmpty(label) ?? String(target.dropFirst()))
            } else if target.hasPrefix("!") {
                out += "@" + (nonEmpty(label) ?? String(target.dropFirst().prefix { $0 != "^" }))
            } else {
                out += nonEmpty(label) ?? String(target)
            }
            rest = after[after.index(after: end)...]
        }
        out += rest
        return out.replacingOccurrences(of: "&lt;", with: "<").replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&amp;", with: "&")
    }

    /// Whitespace collapsed, cut at `limit` characters on a word boundary.
    static func preview(_ text: String, limit: Int = previewCharacters) -> String {
        let collapsed = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        if collapsed.count <= limit {
            return collapsed
        }
        let cut = String(collapsed.prefix(limit))
        let kept = cut.lastIndex(of: " ").map { String(cut[..<$0]) } ?? cut
        return kept.trimmingTrailingWhitespace() + "…"
    }

    /// One topic per conversation, titled with its newest message's preview.
    static func topics(_ messages: [SlackDirectMessage]) -> [Topic] {
        var order: [String] = []
        var conversations: [String: [SlackDirectMessage]] = [:]
        for message in messages {
            if conversations[message.channelID] == nil {
                order.append(message.channelID)
            }
            conversations[message.channelID, default: []].append(message)
        }
        return order.map { channelID in
            let found = conversations[channelID]!.sorted { tsValue($0.ts) < tsValue($1.ts) }
            // Read-only: SilentDesk has no scope to delete a Slack message.
            let items = found.map { message in
                Item(
                    key: message.ts, direction: message.direction, author: message.author.isEmpty ? nil : message.author,
                    url: message.permalink.isEmpty ? nil : message.permalink, date: message.date, deletable: false)
            }
            let title = found.last?.preview ?? ""
            return Topic(key: channelID, title: title.isEmpty ? "(empty message)" : title, items: items, deletable: false)
        }
    }
}

extension String {
    func trimmingTrailingWhitespace() -> String {
        var text = Substring(self)
        while let last = text.last, last.isWhitespace { text.removeLast() }
        return String(text)
    }
}
