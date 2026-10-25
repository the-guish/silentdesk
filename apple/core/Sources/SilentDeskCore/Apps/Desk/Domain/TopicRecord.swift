/// The desk's topics: each connector topic, kept with SilentDesk's own ID.
struct TopicRecord: Sendable, Equatable {
    /// A UUID, made by SilentDesk.
    let id: String
    let service: String
    /// The connector's key for the topic, such as a Gmail thread ID.
    let key: String
    let title: String
    /// One or more, oldest first.
    let items: [Item]
    /// RFC 3339.
    let createdAt: String
    let updatedAt: String
    /// What the connector said: it can delete the whole topic at once. See
    /// `Topics.deletable` for whether the topic can be deleted at all.
    let deletable: Bool
}
