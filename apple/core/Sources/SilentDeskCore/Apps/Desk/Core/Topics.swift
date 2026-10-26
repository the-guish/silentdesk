/// Rules about topics: how a sync changes them, and their order.
enum Topics {
    /// One service's records after its sync: new topics get records, changed
    /// topics update theirs and keep their ID, and gone topics lose theirs.
    /// `records` holds only that service's records.
    static func apply(
        _ records: [TopicRecord], service: String, result: SyncResult, now: String, newID: () -> String
    ) -> [TopicRecord] {
        let old = Dictionary(records.map { ($0.key, $0) }, uniquingKeysWith: { first, _ in first })
        var kept: [TopicRecord] = []
        if !result.complete {
            let removed = Set(result.removed)
            kept = records.filter { !removed.contains($0.key) }
        }
        for topic in result.topics {
            let updated = record(topic, service: service, old: old[topic.key], now: now, newID: newID)
            if let position = kept.firstIndex(where: { $0.key == topic.key }) {
                kept[position] = updated
            } else {
                kept.append(updated)
            }
        }
        return kept
    }

    /// The record for a topic as its connector reports it, keeping the old
    /// record's ID, creation time and project.
    static func record(
        _ topic: Topic, service: String, old: TopicRecord?, now: String, newID: () -> String
    ) -> TopicRecord {
        TopicRecord(
            id: old?.id ?? newID(),
            service: service,
            key: topic.key,
            title: topic.title,
            items: topic.items,
            createdAt: old?.createdAt ?? now,
            // RFC 3339 times in UTC sort as text.
            updatedAt: topic.items.map(\.date).max() ?? now,
            deletable: topic.deletable,
            projectId: old?.projectId,
            // The service owns the status: the last sync's, never an older one.
            status: topic.status)
    }

    /// A topic can be deleted when its connector can delete it at once, or
    /// when every one of its items can be deleted.
    static func deletable(_ record: TopicRecord) -> Bool {
        record.deletable || byItems(record)
    }

    /// The topic can be deleted only item by item: every item can be, and its
    /// connector cannot delete it at once.
    static func byItems(_ record: TopicRecord) -> Bool {
        !record.deletable && !record.items.isEmpty && record.items.allSatisfy(\.deletable)
    }

    static func newestFirst(_ records: [TopicRecord]) -> [TopicRecord] {
        records.sorted { ($0.updatedAt, $0.id) > ($1.updatedAt, $1.id) }
    }
}
