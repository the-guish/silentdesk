/// HTTPS with the system's certificate store and proxy settings, so corporate
/// TLS inspection keeps working (core principle 2).

import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class URLSessionHttp: Http, @unchecked Sendable {
    static let timeout: TimeInterval = 30

    private let session: URLSession
    private let policy: Policy

    /// `allowLoopbackHTTP` lets tests reach a fake server over plain http on this machine.
    init(allowLoopbackHTTP: Bool = false) {
        policy = Policy(allowLoopbackHTTP: allowLoopbackHTTP)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = Self.timeout
        configuration.httpAdditionalHeaders = ["User-Agent": "SilentDesk/\(API.coreVersion)"]
        session = URLSession(configuration: configuration, delegate: policy, delegateQueue: nil)
    }

    func request(
        _ method: String,
        _ url: String,
        headers: [String: String],
        params: [(String, String)],
        json: JSON?,
        form: [(String, String)]?
    ) async throws -> Response {
        let address = URLQuery.append(params, to: url)
        guard let target = URL(string: address), policy.allows(target) else {
            throw ConnectorError.network(nil, "Only https addresses are allowed: \(address)")
        }
        var request = URLRequest(url: target)
        request.httpMethod = method
        for (name, value) in headers {
            request.setValue(value, forHTTPHeaderField: name)
        }
        if let json {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = json.data
        } else if let form {
            request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
            request.httpBody = Data(URLQuery.encode(form).utf8)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw ConnectorError.network(nil, error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw ConnectorError.network(nil, "The answer from \(target.host ?? address) was not HTTP.")
        }
        var fields: [String: String] = [:]
        for (name, value) in http.allHeaderFields {
            fields["\(name)".lowercased()] = "\(value)"
        }
        // A redirect left in place is one the policy refused to follow.
        if (300..<400).contains(http.statusCode), let location = fields["location"] {
            throw ConnectorError.network(nil, "Only https addresses are allowed: \(location)")
        }
        return Response(status: http.statusCode, headers: fields, body: data)
    }

    /// Checks every address before it is requested, redirects included.
    private final class Policy: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
        let allowLoopbackHTTP: Bool

        init(allowLoopbackHTTP: Bool) {
            self.allowLoopbackHTTP = allowLoopbackHTTP
        }

        func allows(_ url: URL) -> Bool {
            switch url.scheme?.lowercased() {
            case "https":
                return true
            case "http":
                return allowLoopbackHTTP && isLoopback(url.host)
            default:
                return false
            }
        }

        func urlSession(
            _ session: URLSession,
            task: URLSessionTask,
            willPerformHTTPRedirection response: HTTPURLResponse,
            newRequest request: URLRequest,
            completionHandler: @escaping @Sendable (URLRequest?) -> Void
        ) {
            if let url = request.url, allows(url) {
                completionHandler(request)
            } else {
                completionHandler(nil)
            }
        }
    }
}

/// localhost, 127.0.0.0/8 and ::1.
func isLoopback(_ host: String?) -> Bool {
    guard let host = host?.lowercased() else { return false }
    if host == "localhost" || host == "::1" || host == "[::1]" {
        return true
    }
    let parts = host.split(separator: ".", omittingEmptySubsequences: false)
    return parts.count == 4 && parts[0] == "127" && parts.allSatisfy { UInt8($0) != nil }
}
