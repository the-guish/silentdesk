/// The topic screen: a topic's items, or its conversation when the service
/// has one, with Reply and Delete where its connector offers them. As the
/// GTK app's topic_page.py.

import Foundation
import Observation
import SilentDeskCore

@MainActor
@Observable
public final class TopicModel {
    /// One row: an item, or a message of the conversation.
    public struct Entry: Sendable, Equatable, Identifiable {
        public let id: String
        public let who: String
        public let direction: Direction?
        public let date: String
        /// Empty for an item: SilentDesk keeps no bodies.
        public let text: String
        /// Opens the item in its service.
        public let url: String?
        /// The row offers its own Delete.
        public let deletable: Bool
    }

    public let desk: any Desk
    public let notices: Notices
    /// What the queue does once the user replied, deleted the topic or
    /// deleted one item.
    public var replied: @MainActor (TopicView) async -> Void = { _ in }
    public var deleted: @MainActor (TopicView) async -> Void = { _ in }
    public var itemDeleted: @MainActor (TopicView) async -> Void = { _ in }

    public private(set) var topic: TopicView
    /// The conversation, once read; nil for a service that keeps none.
    public private(set) var messages: [Message]?
    public private(set) var loading = false
    /// A reply or a delete is on its way.
    public private(set) var sending = false
    public var reply = ""

    public init(topic: TopicView, desk: any Desk, notices: Notices) {
        self.topic = topic
        self.desk = desk
        self.notices = notices
    }

    public var canReply: Bool { Services.canReply.contains(topic.service) }

    public var canSend: Bool {
        !sending && !reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Why the items have no text, for a service that keeps no conversation.
    public var note: String? {
        guard messages == nil else { return nil }
        return "SilentDesk keeps only who wrote each item and when. Open one in "
            + "\(Format.serviceName(topic.service)) to read it."
    }

    public var entries: [Entry] {
        let fallback = Format.serviceName(topic.service)
        if let messages {
            return messages.enumerated().map { index, message in
                Entry(
                    id: "\(index)-\(message.key)", who: message.author ?? fallback, direction: message.direction,
                    date: message.date, text: message.text, url: nil, deletable: false)
            }
        }
        // With one item, deleting it is deleting the topic: the toolbar's
        // button does that.
        let several = topic.items.count > 1
        return topic.items.map { item in
            Entry(
                id: item.key, who: item.author ?? fallback, direction: item.direction, date: item.date,
                text: "", url: item.url, deletable: several && item.deletable)
        }
    }

    /// Shows the topic as the core now has it, such as after one of its
    /// items is deleted: its title can change with its items.
    public func show(_ topic: TopicView) {
        self.topic = topic
    }

    /// Reads the conversation, for a service that keeps one.
    public func loadHistory() async {
        loading = true
        defer { loading = false }
        do {
            messages = try await desk.history(topicID: topic.id)
        } catch let error as ConnectorError where error.kind == .unsupported {
            messages = nil
        } catch {
            notices.fail(error)
        }
    }

    /// Sends the reply box's text as a reply in the topic.
    public func send() async {
        guard canSend else { return }
        sending = true
        do {
            try await desk.reply(topicID: topic.id, body: reply)
        } catch {
            sending = false
            notices.fail(error)
            return
        }
        sending = false
        reply = ""
        notices.post("Reply sent")
        await replied(topic)
    }

    /// Deletes the topic in its service. The window asks first.
    public func delete() async {
        guard !sending else { return }
        sending = true
        do {
            try await desk.delete(topicID: topic.id)
        } catch {
            sending = false
            notices.fail(error)
            return
        }
        sending = false
        await deleted(topic)
    }

    /// Deletes one item in its service. The window asks first.
    public func deleteItem(_ key: String) async {
        guard !sending else { return }
        sending = true
        do {
            try await desk.deleteItem(topicID: topic.id, itemKey: key)
        } catch {
            sending = false
            notices.fail(error)
            return
        }
        sending = false
        // The queue reads the topics again, and `show` gets this one as the
        // core now has it.
        await itemDeleted(topic)
    }
}
