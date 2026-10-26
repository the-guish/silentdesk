/// Wires the app's own adapters into its application.
enum GmailWiring {
    /// Google's OAuth client, from the settings; nil without a client ID.
    static func googleClient(_ settings: any Settings) -> OAuthClient? {
        guard let clientID = settings.googleClientID, !clientID.isEmpty else { return nil }
        return OAuthClient(
            service: GmailRules.service,
            authorizeURL: settings.baseURL("google-accounts", default: "https://accounts.google.com") + "/o/oauth2/v2/auth",
            tokenURL: settings.baseURL("google-oauth", default: "https://oauth2.googleapis.com") + "/token",
            clientID: clientID,
            clientSecret: settings.googleClientSecret,
            // A refresh token, asked for again on every sign-in.
            extra: [("access_type", "offline"), ("prompt", "consent")])
    }

    static func create(
        settings: any Settings, database: any Database, keyring: any Keyring, http: any Http, oauth: any OAuth
    ) -> any Connector {
        let revokeURL = settings.baseURL("google-oauth", default: "https://oauth2.googleapis.com") + "/revoke"
        let api = GmailHTTPAPI(http: http, baseURL: settings.baseURL("gmail", default: "https://gmail.googleapis.com"))
        let authorization = GmailGoogleAuthorization(oauth: oauth, client: googleClient(settings), revokeURL: revokeURL)
        return GmailConnector(
            api: api, authorization: authorization, credentials: GmailKeyringCredentials(keyring: keyring),
            state: GmailSqlcipherStateStore(database: database))
    }
}
