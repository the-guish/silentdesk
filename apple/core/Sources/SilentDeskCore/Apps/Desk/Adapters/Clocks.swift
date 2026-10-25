final class SystemClock: Clock {
    func now() -> String {
        RFC3339.now()
    }
}

/// Always the same time, for repeatable tests (SILENTDESK_TEST_NOW).
final class FixedClock: Clock {
    let fixed: String

    init(_ fixed: String) {
        self.fixed = fixed
    }

    func now() -> String {
        fixed
    }
}
