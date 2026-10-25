/// The user's browser, for sign-in pages.
protocol Browser: Sendable {
    /// Opens an https URL.
    func open(_ url: String) async throws
}
