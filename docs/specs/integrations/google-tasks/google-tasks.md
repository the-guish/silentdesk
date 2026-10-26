# SilentDesk — Google Tasks Integration

## Goal (v1)

Tasks are a topic kind like any other. They live in **Google Tasks**, not in SilentDesk (core principle 4), and appear in the single Topics list next to emails, Slack messages, Jira issues and pull requests. One task maps to one topic.

- **No checkbox and no status changes yet.** Statuses will be designed separately.
- **Only open tasks are pulled.** A task completed in Google disappears at the next sync.
- **The old Tasks tab is gone.** It stored tasks unencrypted in the webview's `localStorage`, which broke core principles 1 and 4.

## Access

- **Same Google OAuth client as Gmail,** but its **own sign-in and refresh token** (`google-tasks-refresh-token` in the OS keychain). Google Tasks can be connected without Gmail, which matters to organizations that won't approve Gmail's restricted scopes.
- **Scopes:**
  - `tasks.readonly`, which is required;
  - `openid email`, used only to show the account in Settings.
  
  SilentDesk cannot create, change or complete tasks.

## Connecting

The same flow as Gmail: system browser, PKCE, loopback redirect.
- SilentDesk checks that `tasks.readonly` was granted.
- It reads the account email from the OpenID userinfo endpoint.
- It stores the refresh token in the keychain and the email in the encrypted vault.
- Reconnecting with a different account clears the old account's tasks.

## Syncing

- **Automatic,** at startup, every 2 minutes and on window focus. See `docs/specs/sync.md`.
- **Fetching:** every task list (`users/@me/lists`), then each list's tasks with `showCompleted=false`, `showHidden=false`, `showDeleted=false` and `showAssigned=true`, 100 per page, at most 20 pages per list.
- **Kept per task:**
  - task and list IDs, and the list title;
  - due day (`YYYY-MM-DD`; Google keeps no time);
  - origin: Gmail, Docs or Chat, from `assignmentInfo` or the task's links;
  - the Google Tasks link and the last-updated date.
- **Topic title:** the task's title. It follows renames on later syncs.
- **Not stored:** the task's notes.
- **Re-sync:** a task already stored keeps its topic. Tasks that are completed or deleted are removed with their topics. Other services' topics are untouched.

## Display

A task row reads "Task · My Tasks · Due Oct 30 · From Gmail". It uses the same row as every other topic; the direction icon shows the task as on the user's plate (inbound). Search matches the list name and origin as well as the title.

## Disconnecting

Revokes the grant at Google, deletes the refresh token, and deletes all local task data.

## Next

- Task statuses and actions: complete, reopen, edit, create. These need the `tasks` scope instead of `tasks.readonly`, so users will have to approve once more.
- Join a task to the topic of the email it came from: tasks created from Gmail carry an `email` link.
- Turn any topic into a task.
