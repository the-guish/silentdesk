/// Google sign-in for Gmail, through the shared OAuth sign-in.
final class GmailGoogleAuthorization: GmailAuthorization {
    private let oauth: any OAuth
    /// Nil when no Google client ID is configured.
    private let client: OAuthClient?
    private let revokeURL: String
    private let service = GmailRules.service

    init(oauth: any OAuth, client: OAuthClient?, revokeURL: String) {
        self.oauth = oauth
        self.client = client
        self.revokeURL = revokeURL
    }

    var configured: Bool { client != nil }

    private func requireClient() throws -> OAuthClient {
        guard let client else {
            throw ConnectorError.auth(service, "Gmail is not configured: set SILENTDESK_GOOGLE_CLIENT_ID.")
        }
        return client
    }

    func signIn(scopes: [String], required: [String]) async throws -> GmailGrant {
        let tokens = try await oauth.signIn(try requireClient(), scopes: scopes)
        guard required.allSatisfy(tokens.scopes.contains) else {
            throw ConnectorError.auth(service, "Gmail access was not granted.")
        }
        guard let access = tokens.accessToken, !access.isEmpty, let refresh = tokens.refreshToken, !refresh.isEmpty else {
            throw ConnectorError.auth(service, "Google did not return a refresh token.")
        }
        return GmailGrant(accessToken: access, refreshToken: refresh)
    }

    func accessToken(refreshToken: String) async throws -> String {
        let tokens = try await oauth.refresh(try requireClient(), refreshToken: refreshToken)
        guard let access = tokens.accessToken, !access.isEmpty else {
            throw ConnectorError.network(service, "Google returned no access token.")
        }
        return access
    }

    func revoke(refreshToken: String) async {
        await oauth.revoke(url: revokeURL, token: refreshToken)
    }
}
