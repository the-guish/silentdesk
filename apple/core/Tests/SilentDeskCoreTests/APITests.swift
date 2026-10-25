@testable import SilentDeskCore
import Testing

@Test func versionReportsTheContractAndCore() {
    #expect(API.version() == Version(contract: API.contract, implementation: "swift", version: API.coreVersion))
}

@Test func theDeskKnowsEveryService() async throws {
    // Building the desk does no I/O, so no keyring or database is needed.
    let settings = LocalSettings(dataDirectory: "/nonexistent", testKeyring: "/nonexistent/keyring.json")
    let desk = API.desk(settings: settings) as? DeskService
    #expect(desk != nil)
}
