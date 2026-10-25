/// `--screenshots DIR`: walks the app through its screens over the demo
/// desk and saves each window as a PNG, light and dark, then quits. CI runs
/// it so the screens can be looked at without a Mac.

import AppKit
import SilentDeskAppModel

@MainActor
struct ScreenshotTour {
    let app: AppState
    let folder: URL

    func run() async {
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let queue = app.queue
        await queue.load()
        NSApp.activate()
        await settle()
        let main = NSApp.keyWindow ?? NSApp.windows.first(where: \.isVisible)
        for (appearance, suffix) in [(NSAppearance.Name.aqua, "light"), (NSAppearance.Name.darkAqua, "dark")] {
            NSApp.appearance = NSAppearance(named: appearance)
            queue.selection = nil
            queue.query = ""
            await settle()
            save("1-queue-\(suffix)", main)

            queue.selection = queue.topics.first { $0.service == "slack" }?.id
            await settle()
            save("2-conversation-\(suffix)", main)

            queue.selection = queue.topics.first { $0.service == "gmail" }?.id
            await settle()
            save("3-items-reply-\(suffix)", main)

            queue.selection = nil
            queue.query = "certificates"
            await settle()
            save("4-search-\(suffix)", main)

            queue.query = "nothing like this"
            await settle()
            save("5-no-match-\(suffix)", main)

            queue.query = ""
            queue.selection = queue.topics.first { $0.service == "tasks" }?.id
            queue.notices.post("Reply sent", seconds: 30)
            await settle()
            save("6-notice-\(suffix)", main)
            queue.notices.shown.forEach { queue.notices.dismiss($0.id) }

            app.openSettings()
            await settle(seconds: 2)
            let settings = NSApp.windows.first { $0.isVisible && $0 !== main }
            save("7-services-\(suffix)", settings)
            settings?.close()
            main?.makeKeyAndOrderFront(nil)
        }
    }

    /// Lets SwiftUI lay out and draw, and the history load.
    private func settle(seconds: Double = 1) async {
        try? await Task.sleep(for: .seconds(seconds))
    }

    /// Saves the window, title bar and toolbar included.
    private func save(_ name: String, _ window: NSWindow?) {
        guard let window,
            let view = window.contentView?.superview ?? window.contentView,
            let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)
        else {
            log("screenshot \(name): no window")
            return
        }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { return }
        let file = folder.appendingPathComponent("\(name).png")
        do {
            try png.write(to: file)
            log("screenshot \(name): \(file.path)")
        } catch {
            log("screenshot \(name): \(error)")
        }
    }
}

/// Straight to stderr, so CI's log has it even as the app quits.
private func log(_ line: String) {
    FileHandle.standardError.write(Data((line + "\n").utf8))
}
