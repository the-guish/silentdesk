/// Text encodings the services use: base64 and percent-encoded queries.

import Foundation

enum Base64 {
    /// Standard base64, with padding.
    static func encode(_ data: Data) -> String {
        data.base64EncodedString()
    }

    /// The URL-safe alphabet (RFC 4648 §5), with or without padding.
    static func encodeURLSafe(_ data: Data, padding: Bool) -> String {
        var text = data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
        if !padding {
            while text.hasSuffix("=") { text.removeLast() }
        }
        return text
    }

    /// Random bytes, from the system's cryptographic generator.
    static func randomBytes(_ count: Int) -> Data {
        var generator = SystemRandomNumberGenerator()
        return Data((0..<count).map { _ in UInt8.random(in: .min ... .max, using: &generator) })
    }
}

enum URLQuery {
    /// RFC 3986's unreserved characters, the only ones sent as they are.
    private static let unreserved = CharacterSet(
        charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

    /// Percent-encodes everything but the unreserved characters.
    static func encode(_ text: String) -> String {
        text.addingPercentEncoding(withAllowedCharacters: unreserved) ?? text
    }

    /// name=value pairs, encoded and joined with '&'.
    static func encode(_ pairs: [(String, String)]) -> String {
        pairs.map { encode($0.0) + "=" + encode($0.1) }.joined(separator: "&")
    }

    /// `url` with `pairs` added to its query.
    static func append(_ pairs: [(String, String)], to url: String) -> String {
        guard !pairs.isEmpty else { return url }
        let separator = url.contains("?") ? (url.hasSuffix("?") || url.hasSuffix("&") ? "" : "&") : "?"
        return url + separator + encode(pairs)
    }

    /// The pairs of a query string, in order, blank values kept; '+' is a space.
    static func parse(_ query: String) -> [(String, String)] {
        query.split(separator: "&", omittingEmptySubsequences: true).map { pair in
            let parts = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            let name = decode(String(parts[0]))
            let value = parts.count > 1 ? decode(String(parts[1])) : ""
            return (name, value)
        }
    }

    static func decode(_ text: String) -> String {
        text.replacingOccurrences(of: "+", with: " ").removingPercentEncoding ?? text
    }
}
