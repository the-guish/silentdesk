/// Sync rounds. See legacy/docs/specs/sync.md.
enum SyncRounds {
    /// Gmail goes last, because its first sync can take minutes.
    static let order = ["tasks", "github", "jira", "slack", "gmail"]

    /// The connected services in the order one round syncs them: the ones in
    /// `order` first, in that order, then any others by name.
    static func roundOrder(_ services: some Sequence<String>) -> [String] {
        let services = Set(services)
        return order.filter(services.contains) + services.subtracting(order).sorted()
    }
}
