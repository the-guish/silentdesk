@testable import SilentDeskCore
import Testing

@Test func versionReportsTheContractAndCore() {
    #expect(API.version() == Version(contract: API.contract, implementation: "swift", version: API.coreVersion))
}
