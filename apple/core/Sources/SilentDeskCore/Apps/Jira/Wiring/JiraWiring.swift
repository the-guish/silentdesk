/// Wires the app's own adapters into its application.
enum JiraWiring {
    /// Atlassian's gateway, the only way in for scoped Jira Cloud API tokens.
    static let gateway = "https://api.atlassian.com/ex/jira"

    static func create(settings: any Settings, database: any Database, keyring: any Keyring, http: any Http) -> any Connector {
        JiraConnector(
            api: JiraHTTPAPI(http: http),
            credentials: JiraKeyringCredentials(keyring: keyring),
            state: JiraSqlcipherStateStore(database: database),
            siteBase: { site in settings.baseURL("jira", default: site) },
            gatewayBase: { settings.baseURL("atlassian", default: gateway) })
    }
}
