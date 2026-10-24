# SilentDesk — Slack Integration

Status: v1 implemented · Last updated: 2026-10-23

## Goal (v1)

Let the user connect their Slack account securely, then pull their **last 10 direct messages, sent and received,** as topics. This covers 1:1 DMs and group DMs. One message maps to one topic; no grouping yet.

## Access

- **User token only,** with two scopes:
  - `search:read`, to find recent direct messages;
  - `users:read`, to show names instead of user IDs.
- **No bot scopes.** SilentDesk cannot post, react, or change anything in Slack.
- **One account** (one user in one workspace) at a time.

Slack has no scope that limits an app to message metadata, the way Gmail's `gmail.metadata` does. `search:read` can search anything the user can see. SilentDesk limits itself to direct messages and stores as little as possible (see below).

## Connecting

1. The user selects **Connect** on the Slack row in the Topics view.
2. SilentDesk opens Slack's approval page in the **system browser**. It uses OAuth v2 with PKCE (S256) and a random `state`, so no client secret exists.
   - The redirect goes to `http://localhost:47615/slack/callback`. Slack matches redirect URLs exactly, so the port is fixed; `SILENTDESK_SLACK_REDIRECT_PORT` overrides it.
   - The loopback listener checks `state`, answers anything else with 404, and gives up after 3 minutes.
3. SilentDesk exchanges the code without a client secret and checks that both scopes were granted.
4. It calls `auth.test` to learn the user and workspace.
5. **Storage:**
   - The token is stored in the OS credential store as `slack-credential`. That is either a long-lived user token, or, with token rotation, an access token plus a refresh token.
   - The user and workspace go into the encrypted vault.
6. SilentDesk then runs a first sync.

Tokens never reach the webview.

## Syncing

- **Automatic,** at startup, every 2 minutes and on window focus. See `docs/specs/sync.md`.
- **Fetching:** two `search.messages` queries sorted by time:
  - `to:me` finds direct messages sent to the user;
  - `from:<@me>` finds messages the user sent.
- **Filtering:** results are kept only if they are in a DM or group DM. Duplicates are dropped, and the 10 newest are kept.
- **Display details:**
  - **Names:** user IDs are resolved with `users.info`, once per user per sync.
  - **Direction:** messages sent by the user are outbound, everything else is inbound.
  - **Counterpart:** the other person for a 1:1 DM, or "Group DM".
- **Topic title:** the message's first 120 characters as plain text, with mentions, channel links and URLs rewritten readably.
- **Re-sync:** a message already stored keeps its topic. Messages that drop out of the last 10 are removed, along with topics left without any source item. Gmail topics are not affected.
- **Expiring tokens:** if token rotation is on, an expired access token is renewed before syncing, and the new refresh token replaces the old one.

## What is stored

In the encrypted vault, per message:
- conversation ID and timestamp;
- direction;
- author name and counterpart;
- permalink;
- date.

The **message text is not stored.** Only the topic title, a preview of at most 120 characters, keeps any of it.

## Disconnecting

**Disconnect** does three things:
1. revokes the token with `auth.revoke` (best effort, renewing it first if it had expired);
2. deletes it from the credential store;
3. deletes the account, its messages and their topics from the vault.

## Failure handling

| Situation | Behaviour |
|-----------|-----------|
| No client ID configured | The Slack row explains how to set one up. |
| Port in use | Sign-in fails and names the setting to change. |
| Redirect URL or client ID wrong | Sign-in fails with a message saying which. |
| Token revoked, expired, or refresh token expired | The token is deleted and the user is asked to connect again. Topics stay. Reconnecting the same user and workspace keeps them; a different account clears them. |
| Rate limited (HTTP 429) | Shown inline with Slack's suggested wait. |
| Another Slack operation is running | A user action waits for it. An automatic sync skips Slack. |

## Corporate deployment

- **Own app.** Each organization creates its own Slack app from `docs/setup/slack-app-manifest.json`. There is no SilentDesk-operated app or server.
- **App approval.** Workspaces that require app approval need an admin to approve it once.
- **Rate limits.** Slack's 2025 rate-limit reductions apply to commercially distributed, non-Marketplace apps. Internal, customer-built apps keep the standard limits.
- **Network.** HTTPS uses the OS TLS stack, trusted certificates and proxy settings. The only host contacted is `slack.com`.

## Risks and next steps

- **`search.messages` is a legacy method.** Slack recommends its newer "Real-time Search API", but that is aimed at AI apps and requires a search query. If `search.messages` is retired, the fallback is listing DMs (`users.conversations`) and reading each one's history. That is slower, and needs `im:history` and `mpim:history`.
- **The search modifiers are not formally documented** for the API. Slack's blog documents `to:me` as finding DMs sent to you; the `from:<@USER>` form is not documented. Both need checking against a real workspace.
- **Next:**
  - include mentions of the user in channels;
  - group messages into topics (by conversation first);
  - open a message in Slack from its permalink.
