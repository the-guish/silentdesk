# SilentDesk — Gmail Integration

Status: v1 implemented · Last updated: 2026-10-23

## Goal (v1)

Let the user connect their Gmail account securely, then pull the **subject of every email in their Inbox** as topics. One email maps to one topic; no grouping yet. From a topic, the user can reply to its email or move it to the trash.

## Access

- **Scopes:**
  - `https://www.googleapis.com/auth/gmail.modify`, to read headers and labels and to move emails to the trash;
  - `https://www.googleapis.com/auth/gmail.send`, to send replies.
- **What SilentDesk does with them.** It requests the `Subject` header, plus the reply headers when the user replies. It never fetches bodies or attachments. It cannot delete an email for good: Gmail empties the trash after 30 days.
- **The scopes allow more.** `gmail.modify` can read bodies and change labels. No narrower Gmail scope allows trashing.
- **One account** at a time.

## Connecting

1. The user selects **Connect Gmail** in the Topics view.
2. SilentDesk opens Google sign-in in the **system browser**. It uses OAuth 2.0 for native apps (RFC 8252): authorization code with PKCE (S256), a random `state`, and a loopback redirect to `127.0.0.1` on a random port. The password, SSO and MFA happen in the browser; SilentDesk never sees them.
3. Google redirects back to the loopback listener, which checks `state` and closes.
   - Requests that are not the redirect are answered with 404.
   - Each read times out after 5 seconds, and the whole sign-in times out after 3 minutes.
4. SilentDesk exchanges the code for tokens and checks that both Gmail scopes were actually granted.
5. **Storage:**
   - The refresh token goes into the OS credential store.
   - The access token stays in memory only, for the duration of one operation.
   - The account's email address goes into the encrypted vault.
6. SilentDesk then runs a first sync.

Tokens never reach the webview. The UI only sees the connection status and topic data.

## Syncing

- **On demand only.** Sync runs when the user selects **Sync** (or right after connecting). There is no background polling and there are no notifications (core principle 6).
- **What it fetches:** every message in the Inbox, excluding drafts and chat messages.
- **Per message:** `Subject`, labels and the internal date.
  - `SENT` label → outbound; anything else → inbound.
  - Each new message gets a topic, titled with its subject, or "(no subject)" if it has none.
- **First sync:** lists the whole Inbox, then reads each message SilentDesk does not have yet.
  - Gmail returns one message per call, at 5 quota units per call. Google allows 15,000 units per user per minute.
  - SilentDesk reads about 40 messages a second, with up to 20 calls in flight. 10,000 emails take about 4 minutes.
  - Rate-limit and server errors are retried 5 times, after 1, 2, 4, 8 and 16 seconds.
  - The vault is saved every 500 messages. An interrupted sync resumes where it stopped.
  - The Settings screen shows the progress ("Syncing 1,200 of 9,800…").
- **Later syncs:** list only the messages that entered the Inbox since the last sync, using Gmail's history ID.
  - Gmail keeps history for about a week. When it is gone, SilentDesk lists the whole Inbox again, and reads only the new messages.
- **Messages stay** after they leave the Inbox, through archiving, a label change or deletion in Gmail. Only **Trash** in SilentDesk and **Disconnect** remove them.
- **The Topics list** renders 200 rows at first, and 200 more each time it is scrolled to the end. Search covers all topics.

## Replying

- **Reply** opens a text box under the topic. The user types the reply and selects **Send**.
- **Recipient:** the sender of a received email, or its `Reply-To` if set. A reply to an email the user sent goes to its original recipients. There is no reply-all yet.
- **Message:** plain text, subject `Re: <subject>`, with `In-Reply-To` and `References` so it joins the Gmail thread. The original is not quoted, so its body is never read.
- **No AI notice.** The user types the reply by hand (core principle 9).
- The reply headers (`From`, `To`, `Reply-To`, `Message-ID`, `References`) are fetched when the user sends.
- The sent reply is not in the Inbox, so no sync brings it in.

## Trashing

- **Trash** asks for confirmation, then moves the email to the Gmail trash.
- SilentDesk then forgets the email, and its topic if nothing else is in it.

Both actions work only on emails SilentDesk has synced.

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
| Another Gmail operation is running | The request is refused ("already running"). Reply and Trash wait for a sync to finish. |
| A synced message was deleted in Gmail | Sync skips it. Trash removes it from SilentDesk. |
| Account connected before replying and trashing existed | Gmail refuses the action. The user is asked to disconnect and connect again. |

## Corporate deployment

- **Own OAuth client.** Each organization registers its own Google Cloud OAuth client (type "Desktop app"), so there is no SilentDesk-operated server or shared client. See `docs/setup/gmail.md`.
- **How the client ID reaches the app.** Through `SILENTDESK_GOOGLE_CLIENT_ID` and `SILENTDESK_GOOGLE_CLIENT_SECRET`, either at runtime or at build time. Google treats a desktop client's secret as non-confidential; PKCE protects the flow.
- **Network.** HTTPS uses the operating system's TLS stack and trusted certificates, so corporate TLS inspection works. `HTTPS_PROXY` / system proxy settings are honoured. The only hosts contacted are `accounts.google.com`, `oauth2.googleapis.com` and `gmail.googleapis.com`.
- **Admin approval.** Google Workspace admins can allow the client ID under *Security → API controls → App access control*.

## Next

- Group emails into topics (by thread first).
- Link tasks to topics.
- Reading a message body on demand. The `gmail.modify` scope already allows it. This needs a decision.
- AI-written replies must carry the AI notice (core principle 8).
