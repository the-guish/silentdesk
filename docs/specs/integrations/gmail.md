# SilentDesk — Gmail Integration

Status: v1 implemented · Last updated: 2026-10-23

## Goal (v1)

Let the user connect their Gmail account securely, then pull their **last 10 emails, inbound and outbound,** as topics. One email maps to one topic; no grouping yet.

## Access

- **Scope:** `https://www.googleapis.com/auth/gmail.metadata` only. It gives read access to headers and labels. SilentDesk cannot read bodies or attachments, send mail, or change anything in the mailbox.
- **One account** at a time.

## Connecting

1. The user selects **Connect Gmail** in the Topics view.
2. SilentDesk opens Google sign-in in the **system browser**. It uses OAuth 2.0 for native apps (RFC 8252): authorization code with PKCE (S256), a random `state`, and a loopback redirect to `127.0.0.1` on a random port. The password, SSO and MFA happen in the browser; SilentDesk never sees them.
3. Google redirects back to the loopback listener, which checks `state` and closes.
   - Requests that are not the redirect are answered with 404.
   - Each read times out after 5 seconds, and the whole sign-in times out after 3 minutes.
4. SilentDesk exchanges the code for tokens and checks that the Gmail scope was actually granted.
5. **Storage:**
   - The refresh token goes into the OS credential store.
   - The access token stays in memory only, for the duration of one operation.
   - The account's email address goes into the encrypted vault.
6. SilentDesk then runs a first sync.

Tokens never reach the webview. The UI only sees the connection status and topic data.

## Syncing

- **On demand only.** Sync runs when the user selects **Sync** (or right after connecting). There is no background polling and there are no notifications (core principle 6).
- **What it fetches:** the 10 most recent messages in the mailbox, in Gmail's order, excluding drafts and chat messages. Spam and Trash are excluded by Gmail's defaults.
- **Per message:** `From`, `To`, `Subject`, labels and the internal date.
  - `SENT` label → outbound; anything else → inbound.
- **Re-sync:**
  - A message already stored keeps its topic.
  - A new message gets a new topic, titled with its subject, or "(no subject)" if it has none.
  - Messages that drop out of the last 10 are removed, along with topics left without any message.

## Disconnecting

**Disconnect** does three things:
1. revokes the grant at Google (best effort);
2. deletes the refresh token from the credential store;
3. deletes the account, its messages and their topics from the vault.

## Failure handling

| Situation | Behaviour |
|-----------|-----------|
| No OAuth client configured | The Topics view explains how to set one up. |
| User denies access, or `state` does not match | Sign-in fails with a message; nothing is stored. |
| Refresh token revoked or expired | The token is deleted and the user is asked to connect again. Topics stay. Reconnecting the same account keeps them; a different account clears them. |
| Network or API error | Shown inline in the Topics view. |
| Another Gmail operation is running | The request is refused ("already running"). |

## Corporate deployment

- **Own OAuth client.** Each organization registers its own Google Cloud OAuth client (type "Desktop app"), so there is no SilentDesk-operated server or shared client. See `docs/setup/gmail.md`.
- **How the client ID reaches the app.** Through `SILENTDESK_GOOGLE_CLIENT_ID` and `SILENTDESK_GOOGLE_CLIENT_SECRET`, either at runtime or at build time. Google treats a desktop client's secret as non-confidential; PKCE protects the flow.
- **Network.** HTTPS uses the operating system's TLS stack and trusted certificates, so corporate TLS inspection works. `HTTPS_PROXY` / system proxy settings are honoured. The only hosts contacted are `accounts.google.com`, `oauth2.googleapis.com` and `gmail.googleapis.com`.
- **Admin approval.** Google Workspace admins can allow the client ID under *Security → API controls → App access control*.

## Next

- Group emails into topics (by thread first).
- Link tasks to topics.
- Reading a message body on demand would need a broader scope (`gmail.readonly`). This needs a decision.
- Sending replies: AI disclosure rules apply (core principles 8 and 9).
