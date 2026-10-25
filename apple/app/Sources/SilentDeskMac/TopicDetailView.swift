/// The topic screen: its items, or its conversation where the service keeps
/// one, with Reply and Delete where its connector offers them.

import AppKit
import SilentDeskAppModel
import SilentDeskCore
import SwiftUI

struct TopicDetailView: View {
    let topic: TopicView
    @State private var model: TopicModel
    @State private var confirming: Confirmation?

    /// What a delete asks about: the whole topic, or one item.
    enum Confirmation: Equatable {
        case topic
        case item(String)
    }

    init(topic: TopicView, queue: QueueModel) {
        self.topic = topic
        let model = TopicModel(topic: topic, desk: queue.desk, notices: queue.notices)
        model.replied = { await queue.replied($0) }
        model.deleted = { await queue.deleted($0) }
        model.itemDeleted = { await queue.itemDeleted($0) }
        _model = State(initialValue: model)
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(spacing: 0) {
                        ForEach(Array(model.entries.enumerated()), id: \.element.id) { index, entry in
                            if index > 0 {
                                Divider().padding(.leading, 56)
                            }
                            EntryRow(entry: entry, service: topic.service, busy: model.sending) {
                                confirming = .item(entry.id)
                            }
                        }
                    }
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color(nsColor: .separatorColor)))
                    if let note = model.note {
                        Text(note)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                    }
                }
                .frame(maxWidth: 760)
                .padding(20)
                .frame(maxWidth: .infinity)
            }
            if model.canReply {
                Divider()
                ReplyBar(model: model)
            }
        }
        .navigationTitle(model.topic.title)
        .navigationSubtitle(Format.serviceName(model.topic.service))
        .toolbar {
            ToolbarItemGroup {
                if model.loading || model.sending {
                    ProgressView().controlSize(.small)
                }
                if model.topic.deletable {
                    Button {
                        confirming = .topic
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .help("Delete (⌘⌫)")
                    .keyboardShortcut(.delete, modifiers: .command)
                    .disabled(model.sending)
                }
            }
        }
        .confirmationDialog(
            deletion.heading, isPresented: isConfirming, titleVisibility: .visible, presenting: confirming
        ) { confirmation in
            Button("Delete", role: .destructive) {
                Task {
                    switch confirmation {
                    case .topic: await model.delete()
                    case .item(let key): await model.deleteItem(key)
                    }
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: { _ in
            Text(deletion.body)
        }
        .onChange(of: topic) { _, topic in model.show(topic) }
        .task { await model.loadHistory() }
    }

    private var deletion: Services.Deletion {
        Services.deletion(model.topic.service, confirming == .topic ? .topic : .item)
    }

    private var isConfirming: Binding<Bool> {
        Binding(get: { confirming != nil }, set: { if !$0 { confirming = nil } })
    }
}

/// One item or message: who, whether it was received or sent and when, its
/// text when there is one, and its buttons.
struct EntryRow: View {
    let entry: TopicModel.Entry
    let service: String
    let busy: Bool
    let delete: () -> Void
    @Environment(\.openURL) private var openURL

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            AvatarView(name: entry.who, size: 32)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.who)
                    .font(.headline)
                    .lineLimit(1)
                Text(Format.itemLine(entry.direction, entry.date, now: Date()))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                if !entry.text.isEmpty {
                    Text(entry.text)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 4)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let url = entry.url.flatMap({ URL(string: $0) }) {
                Button {
                    openURL(url)
                } label: {
                    Label("Open in \(Format.serviceName(service))", systemImage: "arrow.up.forward.square")
                        .labelStyle(.iconOnly)
                }
                .buttonStyle(.borderless)
                .help("Open in \(Format.serviceName(service))")
            }
            if entry.deletable {
                Button(action: delete) {
                    Label("Delete", systemImage: "trash")
                        .labelStyle(.iconOnly)
                }
                .buttonStyle(.borderless)
                .help("Delete")
                .disabled(busy)
            }
        }
        .padding(12)
    }
}

/// The reply box and its Send button. ⌘↩ sends; ↩ starts a new line.
struct ReplyBar: View {
    @Bindable var model: TopicModel

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextEditor(text: $model.reply)
                .font(.body)
                .scrollContentBackground(.hidden)
                .frame(height: 64)
                .padding(6)
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                .overlay(alignment: .topLeading) {
                    if model.reply.isEmpty {
                        Text("Reply")
                            .foregroundStyle(.tertiary)
                            .padding(.horizontal, 11)
                            .padding(.vertical, 6)
                            .allowsHitTesting(false)
                    }
                }
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color(nsColor: .separatorColor)))
                .disabled(model.sending)
                .accessibilityLabel("Reply")
            Button {
                Task { await model.send() }
            } label: {
                Label("Send", systemImage: "arrow.up.circle.fill")
                    .labelStyle(.iconOnly)
                    .font(.system(size: 26))
            }
            .buttonStyle(.borderless)
            .keyboardShortcut(.return, modifiers: .command)
            .disabled(!model.canSend)
            .help("Send (⌘↩)")
        }
        .frame(maxWidth: 760)
        .padding(12)
        .frame(maxWidth: .infinity)
    }
}
