/// Rules about Google Tasks. See docs/specs/integrations/google-tasks/google-tasks.md.

import Foundation

enum TasksRules {
    static let service = "tasks"
    static let tasksReadonly = "https://www.googleapis.com/auth/tasks.readonly"
    /// Read-only access to task lists and tasks. `openid email` only names the account.
    static let scopes = [tasksReadonly, "openid", "email"]
    static let requiredScopes = [tasksReadonly]

    static func isOpen(_ task: GoogleTask) -> Bool {
        !task.completed && !task.deleted
    }

    /// One topic per task, with the task as its one item.
    static func topic(_ task: GoogleTask) -> Topic {
        // SilentDesk has read-only access to Google Tasks.
        let item = Item(key: task.taskID, direction: nil, author: nil, url: task.url, date: task.updated, deletable: false)
        let title = task.title.trimmingCharacters(in: .whitespacesAndNewlines)
        return Topic(key: task.taskID, title: title.isEmpty ? "Untitled task" : title, items: [item], deletable: false)
    }
}
