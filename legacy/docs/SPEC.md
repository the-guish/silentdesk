# SilentDesk — Product Spec

## 1. Purpose

A desktop task tracker for work. _One or two sentences on the problem it solves and why existing tools don't fit._

## 2. Users

- Primary user: _(just you? a small team?)_
- Usage pattern: _(always open in the background? opened a few times a day?)_

## 3. Scope

### In scope (v1)
- Task list home screen: add, complete, delete tasks.
- _..._

### Out of scope (v1)
- _..._

## 4. Data model

### Task
| Field       | Type     | Notes                         |
|-------------|----------|-------------------------------|
| `id`        | string   | UUID                          |
| `title`     | string   | required, single line         |
| `done`      | boolean  |                               |
| `createdAt` | ISO date |                               |
| _notes?_    |          | _free text?_                  |
| _dueDate?_  |          |                               |
| _priority?_ |          | _levels?_                     |
| _project / tags?_ |    |                               |

## 5. Screens

### 5.1 Home — task list
- Add-task input at the top; Enter submits.
- Rows: checkbox, title, delete.
- Filters: All / Active / Done.
- _Sorting? Grouping (today / upcoming / by project)?_

### 5.2 _Task detail?_
### 5.3 _Settings?_

## 6. Behaviour

- Keyboard shortcuts: _(global hotkey to add a task? j/k navigation?)_
- Notifications / reminders: _..._
- System tray / menubar: _..._

## 7. Storage & sync

- v1 (scaffold): localStorage.
- Target: _(SQLite file via Tauri? plain JSON file? cloud sync later?)_

## 8. Platforms

- _macOS / Windows / Linux?_

## 9. Non-functional

- Startup time, offline-first, privacy (no telemetry?), _..._

## 10. Open questions

- _..._
