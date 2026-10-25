/// OAuth sign-in through the browser, with PKCE and a one-shot listener on
/// the loopback interface for the redirect. Ported from the legacy backend.

import Foundation

final class LoopbackOAuth: OAuth {
    static let signInTimeout: Duration = .seconds(180)

    private let http: any Http
    private let browser: any Browser
    private let timeout: Duration

    init(http: any Http, browser: any Browser, timeout: Duration = LoopbackOAuth.signInTimeout) {
        self.http = http
        self.browser = browser
        self.timeout = timeout
    }

    func signIn(_ client: OAuthClient, scopes: [String]) async throws -> Tokens {
        let verifier = Base64.encodeURLSafe(Base64.randomBytes(32), padding: false)
        let challenge = Base64.encodeURLSafe(Hashing.sha256(Data(verifier.utf8)), padding: false)
        let listener = LoopbackListener(
            service: client.service, path: client.path, state: Base64.encodeURLSafe(Base64.randomBytes(16), padding: false))
        try listener.start(port: client.port)
        let code: String
        do {
            defer { listener.stop() }
            let query: [(String, String)] = [
                ("client_id", client.clientID),
                ("redirect_uri", listener.redirectURI),
                ("response_type", "code"),
                (client.scopeParameter, scopes.joined(separator: client.scopeSeparator)),
                ("code_challenge", challenge),
                ("code_challenge_method", "S256"),
                ("state", listener.state),
            ] + client.extra
            do {
                try await browser.open(URLQuery.append(query, to: client.authorizeURL))
            } catch {
                throw ConnectorError.auth(client.service, "Your web browser could not be opened.")
            }
            code = try await listener.code(timeout: timeout)
        }
        let form = [
            ("grant_type", "authorization_code"),
            ("code", code),
            ("code_verifier", verifier),
            ("redirect_uri", listener.redirectURI),
        ]
        return try await token(client, form)
    }

    func refresh(_ client: OAuthClient, refreshToken: String) async throws -> Tokens {
        try await token(client, [("grant_type", "refresh_token"), ("refresh_token", refreshToken)])
    }

    func revoke(url: String, token: String) async {
        // Best effort: the local token goes either way.
        _ = try? await http.request("POST", url, form: [("token", token)])
    }

    private func token(_ client: OAuthClient, _ fields: [(String, String)]) async throws -> Tokens {
        var form = fields + [("client_id", client.clientID)]
        if let secret = client.clientSecret, !secret.isEmpty {
            form.append(("client_secret", secret))
        }
        let response = try await http.request("POST", client.tokenURL, headers: ["Accept": "application/json"], form: form)
        guard let body = try? JSON.parse(response.body), body.object != nil else {
            throw ConnectorError.network(
                client.service, "The sign-in server's answer could not be read (\(response.status)).")
        }
        if !response.isSuccess {
            let error = body["error"]?.string
            if error == "invalid_grant" {
                throw ConnectorError.auth(client.service, "The sign-in has expired or was revoked. Connect again.")
            }
            if error == "invalid_client" || error == "unauthorized_client" {
                throw ConnectorError.auth(client.service, "The OAuth client was rejected. Check its client ID and secret.")
            }
            throw ConnectorError.auth(client.service, "Sign-in failed: \(error ?? String(response.status)).")
        }
        let scope = body["scope"]?.string ?? ""
        return Tokens(
            accessToken: body["access_token"]?.string,
            refreshToken: body["refresh_token"]?.string,
            scopes: scope.split(whereSeparator: \.isWhitespace).map(String.init),
            raw: body)
    }
}
