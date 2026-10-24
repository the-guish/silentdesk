# SilentDesk — Syncing

Status: v1 implemented · Last updated: 2026-10-23

## When

SilentDesk syncs every connected service automatically:

- once at startup;
- every 2 minutes while the app is open;
- when the window comes back into focus, if the last round started more than 30 seconds ago.

**Refresh**, next to the search box, starts a round at once. It shows "Refreshing…" while any round runs. **Sync** in Settings still runs one service at once.

## How

- **One round syncs the services in turn:** Google Tasks, GitHub, Jira, Slack, then Gmail. Gmail goes last, because its first sync can take minutes.
- **Rounds skip services that are not connected.**
- **One operation per service runs at a time.**
  - An automatic sync skips a service that is busy, for example while the user signs in.
  - A user action waits for a running sync, then runs. This covers Sync, Connect, Disconnect, Reply and Trash.

## Quiet by design

Automatic syncs never interrupt the user (core principle 6).

- **No notifications, sounds or badges.**
- **The Topics list updates in place** after each service.
- **The footer shows when topics last changed,** for example "Updated 3 min ago".
- **Errors show on the service's row in Settings,** the same as for a manual sync.
- **Gmail's first sync shows its progress** on the Gmail row, wherever it started.
