/// A value that another thread delivers once, awaited with a time limit.

import Foundation

final class Outcome<Value: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var result: Result<Value, any Error>?
    private var waiter: CheckedContinuation<Value, any Error>?

    var isResolved: Bool {
        lock.lock()
        defer { lock.unlock() }
        return result != nil
    }

    /// Delivers the value, or the error. Only the first delivery counts.
    func resolve(_ outcome: Result<Value, any Error>) {
        lock.lock()
        guard result == nil else {
            lock.unlock()
            return
        }
        result = outcome
        let waiter = self.waiter
        self.waiter = nil
        lock.unlock()
        waiter?.resume(with: outcome)
    }

    /// Waits for the value; after `timeout`, throws what `timedOut` returns.
    func value(timeout: Duration, timedOut: @escaping @Sendable () -> any Error) async throws -> Value {
        try await withThrowingTaskGroup(of: Value.self) { group in
            group.addTask { try await self.wait() }
            group.addTask {
                try await Task.sleep(for: timeout)
                throw timedOut()
            }
            let first = try await group.next()!
            group.cancelAll()
            return first
        }
    }

    private func wait() async throws -> Value {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Value, any Error>) in
                lock.lock()
                if let result {
                    lock.unlock()
                    continuation.resume(with: result)
                } else if Task.isCancelled {
                    lock.unlock()
                    continuation.resume(throwing: CancellationError())
                } else {
                    waiter = continuation
                    lock.unlock()
                }
            }
        } onCancel: {
            lock.lock()
            let waiter = self.waiter
            self.waiter = nil
            lock.unlock()
            waiter?.resume(throwing: CancellationError())
        }
    }
}
