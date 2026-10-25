# SilentDesk — CLI contract

Both cores ship a program named `silentdesk`. The conformance suite tests each core through it. The apps reach the same operations through the core's public API (`silentdesk.api` in Python, `SilentDeskCore` in Swift), one function per command, and use nothing else from the core.

```
silentdesk <command> [arguments]
```

## Output

- **stdout** carries exactly one JSON document, followed by a newline, whether the command succeeds or fails. It is UTF-8.
- **stderr** is for people: logs and warnings. It is not part of the contract, and tests ignore it.
- Field names are camelCase.
- Timestamps are RFC 3339 in UTC, ending in `Z`.
- A field with no value is `null`. Fields are not left out unless a command says so.
- Key order, whitespace and number formatting (`1` or `1.0`) are not part of the contract.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | The command succeeded. |
| 1 | The command ran and failed. |
| 2 | Usage error: missing or unknown command, or wrong arguments. |

## Errors

On failure, stdout holds an error document ([schema](schema/error.json)):

```json
{"error": {"kind": "usage", "message": "Unknown command 'foo'. Commands: version."}}
```

| Kind | Exit code | When |
|------|-----------|------|
| `usage` | 2 | The command line is wrong, including an unknown service name or connect fields that are not a JSON object of strings. |
| `auth` | 1 | The service is not connected, or it rejected the credentials. A sync that gets this deletes the stored credentials. |
| `network` | 1 | The service could not be reached, or its answer could not be read. |
| `remote` | 1 | The service answered with an error. |
| `unsupported` | 1 | The service cannot do this, such as replying to a task. |
| `sync` | 1 | A sync round where one or more services failed; see below. |
| `storage` | 1 | The database cannot be opened, such as when its key is missing from the keyring ([storage.md](storage.md)). |
| `internal` | 1 | Anything unexpected. |

When a sync round fails, the error also lists each failed service, with the kind and message it would have had alone. The other services were synced.

```json
{"error": {"kind": "sync", "message": "1 service failed to sync.", "failures": [
  {"service": "github", "kind": "auth", "message": "GitHub rejected the token. Connect again."}
]}}
```

`message` is for people. Tests check that it is there, not what it says.

## Environment

| Variable | Meaning |
|----------|---------|
| `SILENTDESK_GOOGLE_CLIENT_ID` | The Google OAuth client that Gmail and Google Tasks sign in with. Unset or empty: those services are not configured. |
| `SILENTDESK_GOOGLE_CLIENT_SECRET` | That client's secret, if it has one. |
| `SILENTDESK_SLACK_CLIENT_ID` | The Slack app Slack signs in with, with PKCE enabled. Unset or empty: Slack is not configured. |
| `SILENTDESK_SLACK_REDIRECT_PORT` | The port of Slack's sign-in redirect, `http://localhost:<port>/slack/callback`, which must match the Slack app's redirect URL. Default 47615. |
| `SILENTDESK_TEST_KEYRING` | **Tests only.** A JSON file used instead of the OS credential store; see below. |
| `SILENTDESK_TEST_BASE_URL` | **Tests only.** Every address a core calls at `<url>/<name>` instead of its real host; see below. Plain `http` is then allowed, to loopback addresses only. |
| `SILENTDESK_TEST_BROWSER` | **Tests only.** `follow`: instead of opening a browser for sign-in, the core requests the sign-in page itself and follows its redirects, as a browser would after the user signs in. |
| `SILENTDESK_TEST_NOW` | **Tests only.** A fixed time, in RFC 3339, used instead of the clock. |

### Test addresses

With `SILENTDESK_TEST_BASE_URL`, each real host is replaced by `<url>/<name>`, keeping the rest of the path:

| Name | Real host |
|------|-----------|
| `github` | `https://api.github.com`, or a GitHub Enterprise Server's `https://<host>/api/v3` |
| `jira` | The Jira site |
| `atlassian` | `https://api.atlassian.com/ex/jira` |
| `google-accounts` | `https://accounts.google.com` |
| `google-oauth` | `https://oauth2.googleapis.com` |
| `google-userinfo` | `https://openidconnect.googleapis.com` |
| `tasks` | `https://tasks.googleapis.com` |
| `gmail` | `https://gmail.googleapis.com` |
| `slack` | `https://slack.com` |

### Test keyring

Tests and CI cannot reach GNOME Keyring or the macOS Keychain, so when `SILENTDESK_TEST_KEYRING` is set, a core keeps its secrets in that file instead. The file holds one JSON object mapping entry names ([storage.md](storage.md#secrets)) to values; a missing file is an empty keyring. It stores secrets in plain text, against core principle 1, so it exists only for tests: nothing else may set it.

## Commands

### `version`

Takes no arguments. Reports which contract the core implements ([schema](schema/version.json)).

```json
{"contract": 1, "implementation": "python", "version": "0.1.0"}
```

| Field | Type | Notes |
|-------|------|-------|
| `contract` | integer | The version of this contract the core implements. Raised on every incompatible change. |
| `implementation` | `python` \| `swift` | Which core answered. |
| `version` | string | The core's own version. |

### `services`

Takes no arguments. Lists every service SilentDesk can connect, sorted by `service` ([schema](schema/services.json)).

```json
[
  {"service": "github", "configured": true, "connected": false, "account": null},
  {"service": "gmail", "configured": true, "connected": false, "account": null},
  {"service": "jira", "configured": true, "connected": false, "account": null},
  {"service": "slack", "configured": false, "connected": false, "account": null},
  {"service": "tasks", "configured": true, "connected": false, "account": null}
]
```

| Field | Type | Notes |
|-------|------|-------|
| `service` | string | The service's name: `github`, `gmail`, `jira`, `slack` or `tasks`. |
| `configured` | boolean | The core has what it needs to sign in: for Google services and Slack, a client ID. GitHub and Jira need nothing: the user brings a token. |
| `connected` | boolean | A sign-in is stored: for Google services, a refresh token in the keyring; for GitHub and Jira, a token and its account. |
| `account` | string \| null | The connected account, such as an email address, or `login · host` for GitHub, `name · site` for Jira and `name · workspace` for Slack. `null` when not connected. |

### `topics`

Takes no arguments. Lists every topic, newest first: by `updatedAt`, then by `id`, both descending ([schema](schema/topics.json)). Creates the database on first use.

```json
[
  {
    "id": "5f0c…",
    "service": "gmail",
    "title": "Invoice for October",
    "items": [
      {"key": "18c2…", "direction": "inbound", "author": "Ana Ruiz", "url": null, "date": "2026-10-24T09:12:00Z", "deletable": true}
    ],
    "projectId": null,
    "updatedAt": "2026-10-24T09:12:00Z",
    "deletable": true
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | SilentDesk's own ID for the topic, a UUID. |
| `service` | string | The service every item of the topic comes from. |
| `title` | string | |
| `items` | array | One or more, oldest first. |
| `items[].key` | string | The item's ID in its service, such as a Gmail message ID. |
| `items[].direction` | `inbound` \| `outbound` \| null | |
| `items[].author` | string \| null | Who wrote it, as shown to the user. |
| `items[].url` | string \| null | Opens the item in its own system. |
| `items[].date` | string | RFC 3339. |
| `items[].deletable` | boolean | `delete <topic-id> <item-key>` can delete it. |
| `projectId` | string \| null | The topic's project, or `null` for Default. |
| `updatedAt` | string | The newest item's date. |
| `deletable` | boolean | `delete <topic-id>` can delete the whole topic. |

Each connector says which items the user can delete, and which topics it can delete at once, as of the last sync: Gmail, every message and thread; GitHub, Jira, Google Tasks and Slack, none, as SilentDesk only reads them. A topic whose items are all deletable is deletable too: deleting it deletes them one by one. The service has the last word: if it refuses, as Slack would for a message past the workspace's deletion window, the command fails with its error.

A new topic starts in Default, with `projectId` null. A topic keeps its project across syncs while its service still lists it. A topic that `disconnect` drops loses its project. If it comes back, it starts in Default again.

### `connect <service>`

Connects one service. Reads the service's fields as one JSON object of strings on stdin, such as `{"token": "…"}`; empty input means no fields. Each service lists its fields in its own section. Prints the service's status, as one item of `services` ([schema](schema/status.json)).

| Service | Fields |
|---------|--------|
| `github` | `token`: a personal access token, required. `server`: a GitHub Enterprise Server host, such as `github.acme.com`; empty or missing for github.com. |
| `gmail`, `tasks` | None: they sign in through the browser, with the Google client in `SILENTDESK_GOOGLE_CLIENT_ID`. Each has its own grant and refresh token. |
| `slack` | None: it signs in through the browser, with the Slack app in `SILENTDESK_SLACK_CLIENT_ID`. |
| `jira` | `site`: the Jira site, such as `acme.atlassian.net` or a Data Center address, required. `token`: an API token (Cloud) or personal access token (Data Center), required. `email`: the account's email for Jira Cloud; empty or missing for Data Center. |

### `disconnect <service>`

Disconnects one service: forgets its credentials, its stored state and its topics. Prints the service's status ([schema](schema/status.json)).

### `sync [service]`

Syncs one service, or, without an argument, every connected service in turn: Google Tasks, GitHub, Jira, Slack, then Gmail. Prints when topics last changed ([schema](schema/sync.json)).

```json
{"lastSynced": "2026-10-24T12:00:00Z"}
```

### `history <topic-id>`

A topic's recent messages with their text, oldest first, read live from its service and never stored ([schema](schema/history.json)). Slack shows the conversation's 50 most recent messages, without join and leave events. Services that keep no conversation fail with `unsupported`: Gmail, for one, never reads a message's body.

```json
[{"key": "1761300000.000100", "direction": "inbound", "author": "Bo Lind", "text": "Can you check the deploy?", "date": "2025-10-24T10:00:00Z"}]
```

### `reply <topic-id>`

Replies in a topic, through its service: for Gmail, to the thread's newest message. The reply is plain text on stdin, written by the user, so it carries no AI notice (core principle 9). Prints `{}` ([schema](schema/empty.json)). An empty reply, or an unknown topic ID, is a usage error; a service that cannot reply fails with `unsupported`.

### `delete <topic-id> [item-key]`

Deletes a topic, or with an item key one of its items, in its service, then drops it. For Gmail, the thread or the message moves to the trash, which Gmail empties after 30 days. A topic its connector cannot delete at once is deleted item by item, oldest first; if one fails, the command fails and the items deleted before it stay deleted. After an item is deleted, the topic shows as its service reports it, so its title can change; deleting its last item drops it. Prints `{}` ([schema](schema/empty.json)). An unknown topic ID or item key is a usage error; a topic or item that is not `deletable` fails with `unsupported`.

### `projects`

Takes no arguments. Lists the user's projects, sorted by name, ignoring case ([schema](schema/projects.json)). Default is not in the list. It holds every topic without a project.

```json
[{"id": "9b1e…", "name": "Project-45"}, {"id": "3c7a…", "name": "Project-X"}]
```

### `project add <name>`

Creates a project and prints it ([schema](schema/project.json)). The name is free text, without its leading and trailing spaces. A name is a usage error when it is empty or another project has it. `All` and `Default` are usage errors too, as the filter bar uses them ([filters.md](filters.md)). These checks ignore case.

### `project rename <project-id> <name>`

Renames a project and prints it ([schema](schema/project.json)). The name follows the rules of `project add`. An unknown project ID is a usage error.

### `project delete <project-id>`

Deletes a project. Its topics move back to Default. Prints `{}` ([schema](schema/empty.json)). An unknown project ID is a usage error.

### `move <topic-id> <project-id>`

Moves a topic to a project. The project ID `default` moves it back to Default. Prints `{}` ([schema](schema/empty.json)). An unknown topic or project ID is a usage error.

## Planned

Not part of the contract yet:

- **Options for repeatable runs**, arriving with storage and the first sync: a fixed clock, and a base URL per service so the suite can point the cores at a fake server.
- **Rules that assign new topics to projects.** Until then, every new topic starts in Default.
- **The legacy backend's methods** (`topics.list`, `<source>.sync`, `gmail.reply` and the rest), ported one by one as commands.
