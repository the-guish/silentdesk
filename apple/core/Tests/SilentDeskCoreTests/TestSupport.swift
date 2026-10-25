/// The error of type `E` that `body` throws, or nil when it throws another or none.
func caught<E: Error>(_ type: E.Type, _ body: () throws -> Void) -> E? {
    do {
        try body()
        return nil
    } catch {
        return error as? E
    }
}

func caught<E: Error>(_ type: E.Type, _ body: () async throws -> Void) async -> E? {
    do {
        try await body()
        return nil
    } catch {
        return error as? E
    }
}
