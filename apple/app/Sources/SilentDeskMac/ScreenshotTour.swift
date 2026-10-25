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
        let main = NSApp.keyWindow ?? NSApp.windows.first { $0.isVisible }
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

    /// Saves the window as the window server shows it, with screencapture,
    /// and as its views draw themselves, which misses the sidebar's
    /// translucent material. Both while it is unclear which works on CI.
    private func save(_ name: String, _ window: NSWindow?) {
        guard let window else {
            log("screenshot \(name): no window")
            return
        }
        let file = folder.appendingPathComponent("\(name).png")
        let capture = Process()
        capture.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        capture.arguments = ["-x", "-o", "-l", String(window.windowNumber), file.path]
        do {
            try capture.run()
            capture.waitUntilExit()
            log("screenshot \(name): screencapture exited \(capture.terminationStatus)")
        } catch {
            log("screenshot \(name): \(error)")
        }

        guard let view = window.contentView?.superview ?? window.contentView,
            let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)
        else { return }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { return }
        try? png.write(to: folder.appendingPathComponent("\(name)-drawn.png"))
    }
}

/// Straight to stderr, so CI's log has it even as the app quits.
private func log(_ line: String) {
    FileHandle.standardError.write(Data((line + "\n").utf8))
}
