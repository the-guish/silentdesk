/// Slack sign-in through the shared OAuth sign-in. The Slack app has PKCE
/// enabled, so there is no client secret; only user scopes are asked for.

import Foundation

final class SlackOAuthAuthorization: SlackAuthorization {
    private let oauth: any OAuth
    private let client: OAuthClient?
    private let revokeURL: String
    private let service = SlackRules.service

    init(oauth: any OAuth, client: OAuthClient?, revokeURL: String) {
        self.oauth = oauth
        self.client = client
        self.revokeURL = revokeURL
    }

    var configured: Bool { client != nil }

    private func requireClient() throws -> OAuthClient {
        guard let client else {
            throw ConnectorError.auth(service, "Slack is not configured: set SILENTDESK_SLACK_CLIENT_ID.")
        }
        return client
    }

    func signIn() async throws -> SlackCredential {
        let client = try requireClient()
        let (credential, scope) = try credential(from: try await oauth.signIn(client, scopes: SlackRules.userScopes), client)
        let granted = scope.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        guard SlackRules.userScopes.allSatisfy(granted.contains) else {
            throw ConnectorError.auth(service, "Slack access was not fully granted.")
        }
        return credential
    }

    func refresh(_ credential: SlackCredential) async throws -> SlackCredential {
        guard let refreshToken = credential.refreshToken else {
            throw ConnectorError.auth(service, "The Slack token has expired.")
        }
        let client = try requireClient()
        let (fresh, _) = try self.credential(from: try await oauth.refresh(client, refreshToken: refreshToken), client)
        // With token rotation, Slack may send a new refresh token; else keep the old one.
        return SlackCredential(
            accessToken: fresh.accessToken, refreshToken: fresh.refreshToken ?? credential.refreshToken,
            expiresAt: fresh.expiresAt)
    }

    func revoke(accessToken: String) async {
        await oauth.revoke(url: revokeURL, token: accessToken)
    }

    /// The user token from Slack's answer, which reports errors with ok: false.
    private func credential(from tokens: Tokens, _ client: OAuthClient) throws -> (SlackCredential, String) {
        let body = tokens.raw
        guard body["ok"]?.bool == true else {
            let error = body["error"]?.string ?? "unknown_error"
            if ["invalid_grant", "invalid_refresh_token", "token_expired", "token_revoked"].contains(error) {
                throw ConnectorError.auth(service, "The Slack sign-in has expired or was revoked.")
            }
            if ["invalid_client_id", "bad_client_secret", "invalid_client"].contains(error) {
                throw ConnectorError.auth(service, "Slack rejected the app: check SILENTDESK_SLACK_CLIENT_ID, and that PKCE is on.")
            }
            if error == "bad_redirect_uri" {
                throw ConnectorError.auth(
                    service, "Add http://localhost:\(client.port ?? 0)\(client.path) to the Slack app's redirect URLs.")
            }
            throw ConnectorError.auth(service, "Slack sign-in failed: \(error).")
        }
        let user = body["authed_user"]?.object != nil ? body["authed_user"]! : JSON.object([:])
        // The first exchange puts the user token in authed_user; refreshes, at the top.
        let source = user["access_token"]?.string != nil ? user : body
        guard let access = source["access_token"]?.string else {
            throw ConnectorError.auth(service, "Slack did not return a user token.")
        }
        let expiresAt = source["expires_in"]?.int.map { Int(Date().timeIntervalSince1970) + $0 }
        let credential = SlackCredential(accessToken: access, refreshToken: source["refresh_token"]?.string, expiresAt: expiresAt)
        return (credential, user["scope"]?.string ?? "")
    }
}
