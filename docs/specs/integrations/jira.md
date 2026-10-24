# SilentDesk — Jira Integration

Status: v1 implemented · Last updated: 2026-10-23

## Goal (v1)

Let the user connect Jira securely and pull their **last 10 open issues assigned to them or reported by them,** most recently updated first, as topics. One issue maps to one topic.

- **Inbound:** the issue is assigned to the user. This is work that came to them.
- **Outbound:** the user reported it and someone else, or no one, has it. This is work they are waiting on.

## Why a token, not OAuth

Atlassian's OAuth 2.0 (3LO) still requires a **confidential client secret** and offers no PKCE-only public client for desktop apps. Using it would mean shipping a secret to every machine, or running a SilentDesk server, which goes against core principles 2 and 3. A personal token instead:
- needs no app registration, so an employee can set it up alone;
- can be **read-only** on Jira Cloud, using a scoped API token with `read:jira-work` and `read:jira-user`;
- works the same way on **Jira Data Center**, using a personal access token;
- expires on a schedule the user or admin controls (at most 1 year on Cloud).

If Atlassian adds PKCE for public clients, OAuth can replace this without changing the rest of the integration.

## Connecting

1. The user selects **Connect** on the Jira row in Settings and enters a site, an email (Cloud only) and a token.
2. **Site:** normalized to `https://host[/path]`. Plain `http` is refused.
3. **Choosing the API base:**
   - **Email given → Jira Cloud.** SilentDesk uses HTTP Basic auth and REST API v3, and first calls `GET {site}/rest/api/3/myself`. On 401 for an `*.atlassian.net` site, the token may be a scoped one, which Atlassian only accepts through its gateway. SilentDesk then reads the site's cloud ID from `{site}/_edge/tenant_info` and retries at `https://api.atlassian.com/ex/jira/{cloudId}`.
   - **No email → Jira Data Center.** SilentDesk uses a Bearer token and REST API v2 (`GET {site}/rest/api/2/myself`).
4. **On success:**
   - The credential (email and token) goes into the OS credential store as `jira-credential`.
   - The site, API base, flavor and user go into the encrypted vault.
   - SilentDesk then runs a first sync.
5. **On failure, nothing is stored.** The form keeps the site and email but clears the token.

The token crosses from the UI to the backend once, when the user submits it. After that it never reaches the webview again.

## Syncing

- **Automatic,** at startup, every 2 minutes and on window focus. See `docs/specs/sync.md`.
- **Query:** `(assignee = currentUser() OR reporter = currentUser()) AND statusCategory != Done ORDER BY updated DESC`, at most 10 results.
  - **Cloud** uses `GET /rest/api/3/search/jql`; the older `/search` endpoint has been removed from Jira Cloud.
  - **Data Center** uses `GET /rest/api/2/search`.
- **Fields requested:** `summary, status, assignee, reporter, updated, project`. Descriptions and comments are not requested.
- **Re-sync:** an issue already stored keeps its topic. Issues that close or drop out of the 10 are removed with their topics. Gmail and Slack topics are not affected.

## What is stored

In the encrypted vault, per issue:
- issue ID and key, direction, status, project;
- assignee and reporter display names;
- browse URL and the last-updated date.

The summary becomes the topic title.

## Disconnecting

**Disconnect** deletes the credential from the keychain, and the account, issues and their topics from the vault. Jira has no API for revoking API tokens, so the setup guide tells the user where to revoke it.

## Failure handling

| Situation | Behaviour |
|-----------|-----------|
| Wrong token, or a scoped token without the right scopes | "Jira rejected the token…" Nothing is stored. |
| Wrong site | "No Jira was found at …" |
| `http://` site | Refused before any request is made. |
| Token expired or revoked later | It is deleted, and the user is asked to connect again. Topics stay. Reconnecting the same user and site keeps them; a different account clears them. |
| Another Jira operation is running | A user action waits for it. An automatic sync skips Jira. |

## Corporate deployment

- **Nothing to register.** There is no client ID or `.env` setting for Jira.
- **Admin controls** apply: Atlassian Administration controls API token creation on Cloud, and Data Center admins can limit personal access tokens.
- **Network.** HTTPS uses the OS TLS stack, trusted certificates and proxy settings. The only hosts contacted are the Jira site and, for scoped Cloud tokens, `api.atlassian.com`.

## Risks and next steps

- **`/_edge/tenant_info`** is widely used and endorsed by Atlassian staff, but it is not part of the formal REST API. If it disappears, the cloud ID could be entered manually.
- **Not yet tested** against a real Jira Cloud site or Data Center instance.
- **Next:**
  - issues where the user is mentioned or watching;
  - open an issue in the browser from its URL;
  - link issues to Gmail and Slack topics (an email about PAY-412 belongs with PAY-412).
