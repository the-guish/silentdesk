/// Wires the app's own adapters into its application.
enum SlackWiring {
    static let callbackPath = "/slack/callback"

    /// The organization's Slack app, from the settings; nil without a client ID.
    static func slackClient(_ settings: any Settings) -> OAuthClient? {
        guard let clientID = settings.slackClientID, !clientID.isEmpty else { return nil }
        let base = settings.baseURL("slack", default: "https://slack.com")
        return OAuthClient(
            service: SlackRules.service,
            authorizeURL: base + "/oauth/v2/authorize",
            tokenURL: base + "/api/oauth.v2.access",
            clientID: clientID,
            port: settings.slackRedirectPort,
            path: callbackPath,
            scopeParameter: "user_scope",
            scopeSeparator: ",")
    }

    static func create(
        settings: any Settings, database: any Database, keyring: any Keyring, http: any Http, oauth: any OAuth
    ) -> any Connector {
        let base = settings.baseURL("slack", default: "https://slack.com")
        let authorization = SlackOAuthAuthorization(oauth: oauth, client: slackClient(settings), revokeURL: "\(base)/api/auth.revoke")
        return SlackConnector(
            api: SlackHTTPAPI(http: http, baseURL: "\(base)/api"), authorization: authorization,
            credentials: SlackKeyringCredentials(keyring: keyring), state: SlackSqlcipherStateStore(database: database))
    }
}
