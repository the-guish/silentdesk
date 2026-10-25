/// The main window: the queue on the left, searchable, with when it last
/// changed under it; the open topic on the right.

import AppKit
import SilentDeskAppModel
import SilentDeskCore
import SwiftUI

struct QueueView: View {
    let app: AppState
    @Environment(\.openSettings) private var openSettings

    init(app: AppState) {
        self.app = app
    }

    private var queue: QueueModel { app.queue }

    var body: some View {
        @Bindable var queue = queue
        NavigationSplitView {
            sidebar
                .searchable(text: $queue.query, placement: .sidebar, prompt: "Search topics")
                .navigationSplitViewColumnWidth(min: 260, ideal: 340, max: 480)
                .safeAreaInset(edge: .bottom, spacing: 0) { status }
                .toolbar {
                    ToolbarItem {
                        Button {
                            Task { await queue.refresh() }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .help("Refresh (⌘R)")
                        .disabled(queue.refreshing)
                    }
                }
        } detail: {
            detail
        }
        .overlay(alignment: .bottom) { NoticeView(notices: queue.notices) }
        .task {
            app.openSettings = { openSettings() }
            await app.start()
        }
        .task {
            if app.screenshots == nil {
                await queue.syncPeriodically()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            guard app.screenshots == nil else { return }
            Task { await queue.becameActive() }
        }
    }

    @ViewBuilder
    private var sidebar: some View {
        @Bindable var queue = queue
        switch queue.content {
        case .noMatch:
            ContentUnavailableView.search(text: queue.query)
        case .list, .empty:
            List(selection: $queue.selection) {
                ForEach(queue.shown, id: \.id) { topic in
                    TopicRow(topic: topic)
                }
            }
        }
    }

    /// When topics last changed, rewritten every 30 seconds, and a spinner
    /// while a round runs.
    private var status: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            HStack(spacing: 6) {
                if queue.refreshing {
                    ProgressView().controlSize(.mini)
                }
                Text(queue.status(now: context.date))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .frame(maxWidth: .infinity, minHeight: 28)
        }
        .background(.bar)
    }

    @ViewBuilder
    private var detail: some View {
        if let topic = queue.selectedTopic {
            TopicDetailView(topic: topic, queue: queue)
                .id(topic.id)
        } else if queue.content == .empty {
            ContentUnavailableView {
                Label("No topics yet", systemImage: "tray")
            } description: {
                Text("Connect a service, and its work shows up here.")
            } actions: {
                Button("Connect a Service") { openSettings() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
            }
            .navigationTitle("SilentDesk")
        } else {
            ContentUnavailableView("No Topic Selected", systemImage: "tray", description: Text("Pick a topic on the left."))
                .navigationTitle("SilentDesk")
        }
    }
}

/// One topic in the queue: who wrote last, the title, and when.
struct TopicRow: View {
    let topic: TopicView

    var body: some View {
        HStack(spacing: 10) {
            AvatarView(
                name: Format.avatarName(topic), symbol: topic.service == "tasks" ? "checkmark.square" : "person.fill",
                size: 30)
            VStack(alignment: .leading, spacing: 2) {
                Text(topic.title)
                    .lineLimit(1)
                Text(Format.subtitle(topic))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 4)
            Text(Format.shortDate(topic.updatedAt, now: Date()))
                .font(.caption)
                .foregroundStyle(.secondary)
                .monospacedDigit()
        }
        .padding(.vertical, 4)
    }
}

/// A round avatar with someone's initials, in a color of their own, or a
/// symbol when there is nobody to name.
struct AvatarView: View {
    let name: String?
    var symbol = "person.fill"
    var size: CGFloat = 32

    private static let colors: [Color] = [.blue, .indigo, .purple, .pink, .red, .orange, .green, .teal, .cyan, .brown]

    var body: some View {
        let initials = name.map(Format.initials) ?? ""
        let color = name.map { Self.colors[Format.colorIndex($0, count: Self.colors.count)] } ?? .gray
        Circle()
            .fill(color.gradient)
            .frame(width: size, height: size)
            .overlay {
                if initials.isEmpty {
                    Image(systemName: symbol)
                        .font(.system(size: size * 0.45))
                        .foregroundStyle(.white)
                } else {
                    Text(initials)
                        .font(.system(size: size * 0.4, weight: .semibold))
                        .foregroundStyle(.white)
                }
            }
            .accessibilityHidden(true)
    }
}

/// The newest notice, at the bottom of the window, for a few seconds.
struct NoticeView: View {
    let notices: Notices

    var body: some View {
        if let notice = notices.current {
            Text(notice.text)
                .font(.callout)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(.regularMaterial, in: Capsule())
                .overlay(Capsule().strokeBorder(Color(nsColor: .separatorColor)))
                .shadow(radius: 6, y: 2)
                .padding(.bottom, 18)
                .padding(.horizontal, 24)
                .onTapGesture { notices.dismiss(notice.id) }
                .task(id: notice.id) {
                    try? await Task.sleep(for: .seconds(notice.seconds))
                    notices.dismiss(notice.id)
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .accessibilityAddTraits(.updatesFrequently)
        }
    }
}
