protocol Clock: Sendable {
    /// The current time in RFC 3339, UTC.
    func now() -> String
}
