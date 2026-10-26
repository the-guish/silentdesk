/// Rules about Gmail: threads as topics, and replies. See
/// docs/specs/integrations/gmail.md.

import Foundation

enum GmailRules {
    static let service = "gmail"
    /// gmail.modify reads headers and moves messages to the trash; it cannot
    /// delete them for good. gmail.send sends replies.
    static let scopes = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]

    /// The IDs not known yet, in order and without repeats.
    static func newIDs(known: Set<String>, _ ids: [String]) -> [String] {
        var seen = known
        var out: [String] = []
        for id in ids where !seen.contains(id) {
            seen.insert(id)
            out.append(id)
        }
        return out
    }

    /// One topic per thread, its messages oldest first, titled with the first
    /// message's subject.
    static func topic(threadID: String, messages: [GmailMessage]) -> Topic {
        let ordered = messages.sorted { ($0.date, $0.messageID) < ($1.date, $1.messageID) }
        let items = ordered.map { message in
            let author = senderName(message.sender)
            return Item(
                key: message.messageID,
                direction: message.direction,
                author: author.isEmpty ? nil : author,
                url: "https://mail.google.com/mail/#all/\(threadID)",
                date: message.date,
                // gmail.modify moves any message to the trash.
                deletable: true)
        }
        let subject = (ordered.first?.subject ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return Topic(key: threadID, title: subject.isEmpty ? "(no subject)" : subject, items: items, deletable: true)
    }

    /// `Ana Ruiz <ana@example.com>` -> `Ana Ruiz`; a bare address stays as is.
    static func senderName(_ sender: String) -> String {
        let parts = sender.split(separator: "<", maxSplits: 1, omittingEmptySubsequences: false)
        let name = parts[0].trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        if !name.isEmpty {
            return name
        }
        let address = parts.count > 1 ? String(parts[1]) : ""
        return address.trimmingCharacters(in: CharacterSet(charactersIn: ">")).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The sender (or its Reply-To) of a received email, and the original
    /// recipients of one the user sent. There is no reply-all yet.
    static func recipient(_ original: GmailOriginal) -> String {
        if original.direction == .outbound {
            return original.to
        }
        return original.replyTo.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? original.sender : original.replyTo
    }

    static func replySubject(_ subject: String) -> String {
        let trimmed = subject.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "Re:"
        }
        return trimmed.prefix(3).lowercased() == "re:" ? trimmed : "Re: \(trimmed)"
    }

    /// Header values stay on one line, or they could inject headers. A CR LF
    /// pair is one Character to Swift, so line breaks are found by scalar.
    static func clean(_ value: String) -> String {
        value.split(whereSeparator: { $0.unicodeScalars.allSatisfy { $0 == "\r" || $0 == "\n" } })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    /// RFC 2047 encoding for a header with non-ASCII text.
    static func encodeWord(_ value: String) -> String {
        value.utf8.allSatisfy { $0 < 128 } ? value : "=?UTF-8?B?\(Base64.encode(Data(value.utf8)))?="
    }

    /// The RFC 5322 reply, with CRLF line endings. Nothing is quoted, so the
    /// original's body is never read. Gmail fills in From and Date.
    static func reply(_ original: GmailOriginal, body: String) -> String {
        var headers = [("To", clean(recipient(original))), ("Subject", encodeWord(clean(replySubject(original.subject))))]
        let headerID = clean(original.headerID)
        if !headerID.isEmpty {
            headers += [("In-Reply-To", headerID), ("References", clean("\(original.references) \(headerID)"))]
        }
        headers += [
            ("MIME-Version", "1.0"),
            ("Content-Type", "text/plain; charset=UTF-8"),
            ("Content-Transfer-Encoding", "base64"),
        ]
        let normalized = body.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\n", with: "\r\n")
        let encoded = Array(Base64.encode(Data(normalized.utf8)))
        let lines = stride(from: 0, to: encoded.count, by: 76).map { String(encoded[$0..<min($0 + 76, encoded.count)]) }
        return headers.map { "\($0.0): \($0.1)\r\n" }.joined() + "\r\n" + lines.map { $0 + "\r\n" }.joined()
    }
}
