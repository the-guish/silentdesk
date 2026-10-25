/// The settings the app runs the core with. An app opened from the Finder
/// gets no shell variables, so the sign-in apps' client IDs can also be kept
/// in the app's defaults:
///
///     defaults write com.silentdesk.app SILENTDESK_GOOGLE_CLIENT_ID "…"
///
/// The environment wins over the defaults. Only these variables are read
/// from the defaults; the test variables of spec/cli.md stay in the
/// environment.

import Foundation
import SilentDeskCore

public enum AppSettings {
    public static let fromDefaults = [
        "SILENTDESK_GOOGLE_CLIENT_ID",
        "SILENTDESK_GOOGLE_CLIENT_SECRET",
        "SILENTDESK_SLACK_CLIENT_ID",
        "SILENTDESK_SLACK_REDIRECT_PORT",
    ]

    /// The environment, with each variable in `fromDefaults` it leaves empty
    /// taken from `defaults` when that holds text.
    public static func environment(_ environment: [String: String], defaults: (String) -> Any?) -> [String: String] {
        var merged = environment
        for name in fromDefaults where (environment[name] ?? "").isEmpty {
            switch defaults(name) {
            case let text as String where !text.isEmpty:
                merged[name] = text
            case let number as Int:
                merged[name] = String(number)
            default:
                break
            }
        }
        return merged
    }

    public static func current(
        environment: [String: String] = ProcessInfo.processInfo.environment, defaults: UserDefaults = .standard
    ) -> LocalSettings {
        LocalSettings.fromEnvironment(Self.environment(environment) { defaults.object(forKey: $0) })
    }
}
