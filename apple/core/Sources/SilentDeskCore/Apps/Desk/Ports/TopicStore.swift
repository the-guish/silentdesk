/// The desk's own tables in the shared database.
protocol TopicStore: Sendable {
    func topics() async throws -> [TopicRecord]

    /// Replaces every topic of one service, in one transaction.
    func replace(_ service: String, with records: [TopicRecord]) async throws

    func lastSynced() async throws -> String?

    func setLastSynced(_ when: String) async throws
}
