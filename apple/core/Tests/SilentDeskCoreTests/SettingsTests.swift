@testable import SilentDeskCore
import Testing

@Test func settingsComeFromTheEnvironmentWithEmptyValuesUnset() {
    let settings = LocalSettings.fromEnvironment([
        "HOME": "/home/ana",
        "XDG_DATA_HOME": "/data/",
        "SILENTDESK_GOOGLE_CLIENT_ID": "",
        "SILENTDESK_SLACK_CLIENT_ID": "1.2",
        "SILENTDESK_SLACK_REDIRECT_PORT": "47699",
        "SILENTDESK_TEST_BASE_URL": "http://127.0.0.1:9/",
        "SILENTDESK_TEST_BROWSER": "follow",
        "SILENTDESK_TEST_NOW": "2026-10-24T12:00:00Z",
    ])
    #expect(settings.dataDirectory == "/data/silentdesk")
    #expect(settings.googleClientID == nil)
    #expect(settings.slackClientID == "1.2")
    #expect(settings.slackRedirectPort == 47699)
    #expect(settings.testBaseURL == "http://127.0.0.1:9")
    #expect(settings.testBrowser)
    #expect(settings.now == "2026-10-24T12:00:00Z")
    #expect(settings.baseURL("github", default: "https://api.github.com") == "http://127.0.0.1:9/github")
    #expect(LocalSettings(dataDirectory: "/d").baseURL("github", default: "https://api.github.com") == "https://api.github.com")
    #expect(LocalSettings.port(nil) == 47615)
    #expect(LocalSettings.port("0") == 47615)
    #expect(LocalSettings.port("70000") == 47615)
    #expect(LocalSettings.port("8x") == 47615)
    #expect(LocalSettings.port("8080") == 8080)
}

@Test func theDataFolderFollowsTheHome() {
    let folder = LocalSettings.dataDirectory(["HOME": "/home/ana"])
    #if os(macOS)
    #expect(folder == "/home/ana/Library/Application Support/SilentDesk")
    #else
    #expect(folder == "/home/ana/.local/share/silentdesk")
    #endif
}
