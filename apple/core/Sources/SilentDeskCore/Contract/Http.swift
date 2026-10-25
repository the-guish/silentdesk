/// HTTPS requests to the services the apps connect.

import Foundation

struct Response: Sendable {
    let status: Int
    /// Header names in lowercase.
    let headers: [String: String]
    let body: Data

    var isSuccess: Bool { (200..<300).contains(status) }
}

protocol Http: Sendable {
    /// Sends one request, with a `json` or `form` body if given. A repeated
    /// query name repeats the parameter, as in ?a=1&a=2. Only https URLs,
    /// except loopback addresses when tests allow it. Throws a `network`
    /// error when the service cannot be reached; error statuses are
    /// returned, for each app to interpret.
    func request(
        _ method: String,
        _ url: String,
        headers: [String: String],
        params: [(String, String)],
        json: JSON?,
        form: [(String, String)]?
    ) async throws -> Response
}

extension Http {
    func request(
        _ method: String,
        _ url: String,
        headers: [String: String] = [:],
        params: [(String, String)] = [],
        json: JSON? = nil,
        form: [(String, String)]? = nil
    ) async throws -> Response {
        try await request(method, url, headers: headers, params: params, json: json, form: form)
    }
}
