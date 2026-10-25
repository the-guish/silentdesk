/// Wires the app's own adapters into its application.
enum GitHubWiring {
    static func create(settings: any Settings, database: any Database, keyring: any Keyring, http: any Http) -> any Connector {
        GitHubConnector(
            api: GitHubHTTPAPI(http: http),
            credentials: GitHubKeyringCredentials(keyring: keyring),
            state: GitHubSqlcipherStateStore(database: database),
            apiBase: { endpoint in settings.baseURL("github", default: endpoint.apiBase) })
    }
}
