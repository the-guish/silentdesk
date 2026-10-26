/// The app: one window with the queue and the open topic, and the Services
/// settings.

import AppKit
import SilentDeskAppModel
import SilentDeskCore
import SwiftUI

@main
struct SilentDeskApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var app = AppState(arguments: CommandLine.arguments)

    var body: some Scene {
        Window("SilentDesk", id: "main") {
            QueueView(app: app)
                .frame(minWidth: 720, minHeight: 440)
        }
        .defaultSize(width: 960, height: 640)
        .commands { AppCommands(app: app) }

        Settings {
            SettingsView(services: app.services)
        }
    }
}

/// What every window shares: the desk and the models over it.
@MainActor
@Observable
final class AppState {
    let queue: QueueModel
    let services: ServicesModel
    /// Where `--screenshots` saves the screens, for CI.
    let screenshots: URL?
    /// Opens the settings; set by the main window, which has the action.
    var openSettings: () -> Void = {}

    /// `--demo` shows made-up topics instead of the user's; `--screenshots
    /// DIR` does too, saves each screen to DIR, and quits.
    init(arguments: [String]) {
        screenshots = arguments.firstIndex(of: "--screenshots").flatMap { index in
            arguments.indices.contains(index + 1) ? URL(fileURLWithPath: arguments[index + 1]) : nil
        }
        let demo = screenshots != nil || arguments.contains("--demo")
        let desk: any Desk = demo ? DemoDesk() : API.desk(settings: AppSettings.current())
        queue = QueueModel(desk: desk)
        services = ServicesModel(desk: desk)
        services.changed = { [queue] service, connected in
            await queue.serviceChanged(service, connected: connected)
        }
    }

    /// Runs once the window is up: the topics as they are, then a round.
    func start() async {
        if let screenshots {
            await ScreenshotTour(app: self, folder: screenshots).run()
            NSApp.terminate(nil)
            return
        }
        await queue.load()
        await queue.becameActive()
    }

    func showAbout() {
        let credits = NSAttributedString(
            string: "Your work from Gmail, Google Tasks, GitHub, Jira and Slack, in one quiet queue.",
            attributes: [.font: NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)])
        NSApp.orderFrontStandardAboutPanel(options: [.credits: credits])
        NSApp.activate()
    }

    /// Puts the cursor in the queue's search field.
    func focusSearch() {
        guard let window = NSApp.keyWindow ?? NSApp.mainWindow,
            let root = window.contentView?.superview ?? window.contentView,
            let field = firstSearchField(in: root)
        else { return }
        window.makeFirstResponder(field)
    }

    private func firstSearchField(in view: NSView) -> NSSearchField? {
        if let field = view as? NSSearchField { return field }
        for subview in view.subviews {
            if let field = firstSearchField(in: subview) { return field }
        }
        return nil
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) {
        // A dock icon and a menu bar even when run outside the bundle, as
        // with `swift run`.
        NSApp.setActivationPolicy(.regular)
    }

    /// Like the GTK app, closing the window quits.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

struct AppCommands: Commands {
    let app: AppState

    var body: some Commands {
        CommandGroup(replacing: .appInfo) {
            Button("About SilentDesk") { app.showAbout() }
        }
        CommandGroup(replacing: .newItem) {}
        CommandGroup(before: .toolbar) {
            Button("Refresh") {
                Task { await app.queue.refresh() }
            }
            .keyboardShortcut("r")
            Button("Search Topics") { app.focusSearch() }
                .keyboardShortcut("f")
            Divider()
        }
    }
}
