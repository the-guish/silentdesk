/// OAuth 2.0 sign-in through the user's browser, for any provider: the
/// authorization code flow with PKCE (RFC 7636) and a loopback redirect (RFC
/// 8252). The browser does the sign-in, so SilentDesk never sees the user's
/// password, and SSO or MFA work as usual.

/// An OAuth client an organization registered with a provider.
struct OAuthClient: Sendable {
    /// The service it signs in to, named in errors.
    let service: String
    let authorizeURL: String
    let tokenURL: String
    let clientID: String
    /// Desktop clients may get a secret that is not confidential; PKCE
    /// protects the flow either way.
    let clientSecret: String?
    /// More authorization parameters, such as access_type=offline.
    let extra: [(String, String)]
    /// Where the provider redirects: any free loopback port at "/", or, for
    /// providers that match the registered URL exactly, a fixed port and path.
    let port: Int?
    let path: String
    /// How scopes are sent: Slack, for one, wants user_scope=a,b.
    let scopeParameter: String
    let scopeSeparator: String

    init(
        service: String,
        authorizeURL: String,
        tokenURL: String,
        clientID: String,
        clientSecret: String? = nil,
        extra: [(String, String)] = [],
        port: Int? = nil,
        path: String = "/",
        scopeParameter: String = "scope",
        scopeSeparator: String = " "
    ) {
        self.service = service
        self.authorizeURL = authorizeURL
        self.tokenURL = tokenURL
        self.clientID = clientID
        self.clientSecret = clientSecret
        self.extra = extra
        self.port = port
        self.path = path
        self.scopeParameter = scopeParameter
        self.scopeSeparator = scopeSeparator
    }
}

struct Tokens: Sendable {
    let accessToken: String?
    let refreshToken: String?
    let scopes: [String]
    /// The whole token response, for providers that add their own fields.
    let raw: JSON
}

protocol OAuth: Sendable {
    /// Opens the provider's sign-in page, waits for it to redirect back, and
    /// exchanges the code. Throws an `auth` error when the user declines, the
    /// sign-in times out, or the provider refuses.
    func signIn(_ client: OAuthClient, scopes: [String]) async throws -> Tokens

    /// A new access token. Throws an `auth` error when the grant is gone.
    func refresh(_ client: OAuthClient, refreshToken: String) async throws -> Tokens

    /// Asks the provider to end the grant. Best effort: it never throws.
    func revoke(url: String, token: String) async
}

// Secrets never reach a description, so they cannot leak through an error
// message or a log; the Python core's contract hides the same fields.

extension OAuthClient: CustomStringConvertible {
    var description: String {
        "OAuthClient(service: \(service), clientID: \(clientID), clientSecret: \(clientSecret == nil ? "none" : "hidden"))"
    }
}

extension Tokens: CustomStringConvertible {
    var description: String {
        "Tokens(accessToken: \(accessToken == nil ? "none" : "hidden"), refreshToken: \(refreshToken == nil ? "none" : "hidden"),"
            + " scopes: \(scopes))"
    }
}
