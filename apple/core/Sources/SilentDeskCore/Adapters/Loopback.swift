/// A one-shot listener on the loopback interface, for the redirect that ends
/// an OAuth sign-in (RFC 8252).

import Foundation
#if canImport(Glibc)
import Glibc
#elseif canImport(Darwin)
import Darwin
#endif

final class LoopbackListener: @unchecked Sendable {
    private static let maxRequestBytes = 8 * 1024
    private static let notFound = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

    let service: String
    let path: String
    let state: String
    /// Where the provider sends the browser, once started.
    private(set) var redirectURI = ""

    private let outcome = Outcome<String>()
    private let lock = NSLock()
    private var stopped = false

    init(service: String, path: String, state: String) {
        self.service = service
        self.path = path
        self.state = state
    }

    /// Listens on `port`, or any free one, and serves on its own thread.
    func start(port: Int?) throws {
        #if canImport(Glibc)
        let descriptor = socket(AF_INET, Int32(SOCK_STREAM.rawValue), 0)
        #else
        let descriptor = socket(AF_INET, SOCK_STREAM, 0)
        #endif
        guard descriptor >= 0 else { throw ConnectorError.network(service, "A socket could not be opened.") }
        var enabled: Int32 = 1
        setsockopt(descriptor, SOL_SOCKET, SO_REUSEADDR, &enabled, socklen_t(MemoryLayout<Int32>.size))

        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = UInt16(port ?? 0).bigEndian
        address.sin_addr = in_addr(s_addr: in_addr_t(0x7F00_0001).bigEndian)
        let size = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bound = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(descriptor, $0, size) }
        }
        guard bound == 0, listen(descriptor, 16) == 0 else {
            let code = errno
            closeDescriptor(descriptor)
            if code == EADDRINUSE {
                throw ConnectorError.auth(service, "Port \(port ?? 0) is already in use, so sign-in cannot start.")
            }
            throw ConnectorError.network(service, String(cString: strerror(code)))
        }

        var actual = sockaddr_in()
        var actualSize = size
        _ = withUnsafeMutablePointer(to: &actual) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(descriptor, $0, &actualSize) }
        }
        let actualPort = Int(UInt16(bigEndian: actual.sin_port))
        // Any-port providers (Google) take the address; fixed-port ones
        // (Slack) must match the registered URL, written with localhost.
        redirectURI = port.map { "http://localhost:\($0)\(path)" } ?? "http://127.0.0.1:\(actualPort)"

        let thread = Thread { [self] in self.serve(descriptor) }
        thread.start()
    }

    /// The code the provider sent back; after `timeout`, an auth error.
    func code(timeout: Duration) async throws -> String {
        try await outcome.value(timeout: timeout) { [service] in
            ConnectorError.auth(service, "Sign-in did not finish in time. Try again.")
        }
    }

    /// Stops serving. The thread closes the socket as it ends.
    func stop() {
        lock.lock()
        stopped = true
        lock.unlock()
    }

    private var isStopped: Bool {
        lock.lock()
        defer { lock.unlock() }
        return stopped
    }

    private func serve(_ descriptor: Int32) {
        while true {
            var waiting = pollfd(fd: descriptor, events: Int16(POLLIN), revents: 0)
            let ready = poll(&waiting, 1, 100)
            if isStopped || (ready < 0 && errno != EINTR) {
                break
            }
            guard ready > 0 else { continue }
            let client = accept(descriptor, nil, nil)
            guard client >= 0 else { continue }
            handle(client)
        }
        closeDescriptor(descriptor)
    }

    private func handle(_ client: Int32) {
        var timeout = timeval()
        timeout.tv_sec = 5
        setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        #if canImport(Darwin)
        var enabled: Int32 = 1
        setsockopt(client, SOL_SOCKET, SO_NOSIGPIPE, &enabled, socklen_t(MemoryLayout<Int32>.size))
        #endif

        var request: [UInt8] = []
        var buffer = [UInt8](repeating: 0, count: 4096)
        while request.count < Self.maxRequestBytes, !request.endsHeaders {
            let count = recv(client, &buffer, min(buffer.count, Self.maxRequestBytes - request.count), 0)
            guard count > 0 else { break }
            request.append(contentsOf: buffer[0..<count])
        }
        let text = String(decoding: request, as: UTF8.self)
        let requestLine = text.split(whereSeparator: \.isNewline).first.map(String.init) ?? ""
        let result = outcome(of: requestLine)

        let response: String
        if let result, !outcome.isResolved {
            let message: String
            switch result {
            case .success: message = "Sign-in received. You can close this tab and return to SilentDesk."
            case .failure: message = "Sign-in did not complete. Return to SilentDesk for details."
            }
            let body = "<!doctype html><meta charset=utf-8><title>SilentDesk</title>"
                + "<body style=\"font-family:system-ui;margin:3rem\"><p>\(message)</p>"
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                + "Content-Length: \(body.utf8.count)\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n" + body
        } else {
            response = Self.notFound
        }
        write(response, to: client)
        closeDescriptor(client)
        if let result {
            outcome.resolve(result.mapError { $0 as any Error })
        }
    }

    /// The code, the error to report, or nil for anything that is not the
    /// redirect, such as the browser asking for a favicon.
    func outcome(of requestLine: String) -> Result<String, ConnectorError>? {
        let parts = requestLine.split(separator: " ")
        guard parts.count >= 2, parts[0] == "GET" else { return nil }
        let target = String(parts[1])
        let split = target.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
        guard split[0] == path else { return nil }
        // The first value of a repeated name wins.
        var parameters: [String: String] = [:]
        for (name, value) in URLQuery.parse(split.count > 1 ? String(split[1]) : "") where parameters[name] == nil {
            parameters[name] = value
        }
        let code = parameters["code"]
        let error = parameters["error"]
        if code == nil && error == nil {
            return nil
        }
        if parameters["state"] != state {
            return .failure(.auth(service, "The sign-in response did not match this request."))
        }
        if let error {
            return .failure(.auth(service, error == "access_denied" ? "Access was denied." : "Sign-in failed: \(error)."))
        }
        return .success(code ?? "")
    }

    private func write(_ text: String, to client: Int32) {
        let bytes = Array(text.utf8)
        var sent = 0
        while sent < bytes.count {
            #if canImport(Glibc)
            let count = bytes[sent...].withUnsafeBufferPointer { send(client, $0.baseAddress, $0.count, Int32(MSG_NOSIGNAL)) }
            #else
            let count = bytes[sent...].withUnsafeBufferPointer { send(client, $0.baseAddress, $0.count, 0) }
            #endif
            guard count > 0 else { return }
            sent += count
        }
    }
}

private extension [UInt8] {
    /// The request's headers have ended: a blank line was read.
    var endsHeaders: Bool {
        guard count >= 4 else { return false }
        for index in 0...(count - 4) where self[index] == 0x0D && self[index + 1] == 0x0A && self[index + 2] == 0x0D && self[index + 3] == 0x0A {
            return true
        }
        return false
    }
}

private func closeDescriptor(_ descriptor: Int32) {
    #if canImport(Glibc)
    _ = Glibc.close(descriptor)
    #else
    _ = Darwin.close(descriptor)
    #endif
}
