# Set up Google Tasks access

Google Tasks uses the **same Google OAuth client as Gmail** (see [gmail.md](gmail.md)), but signs in separately with **read-only** access to your tasks. You can connect Google Tasks without connecting Gmail.

## 1. Allow Tasks in your Google Cloud project

In the [Google Cloud console](https://console.cloud.google.com/), in the project that holds your SilentDesk OAuth client:

1. **Enable the Google Tasks API.** Go to *APIs & Services → Library*, search for "Google Tasks API", and select **Enable**.
2. **Add the scopes** under *Google Auth Platform → Data access*:
   - `https://www.googleapis.com/auth/tasks.readonly`, read-only access to task lists and tasks;
   - `openid` and `email`, which only show which account is connected.

If you don't have an OAuth client yet, create one first, following steps 1–5 of [gmail.md](gmail.md). The Gmail scopes are only needed if you also connect Gmail.

## 2. Give the client to SilentDesk

These are the same two settings Gmail uses, in `.env`:

```sh
SILENTDESK_GOOGLE_CLIENT_ID=1234-abc.apps.googleusercontent.com
SILENTDESK_GOOGLE_CLIENT_SECRET=GOCSPX-...
```

Then start the app with `linux/gtk/run.sh`.

## 3. Connect

Open **Settings** (the gear button) and select **Connect** on the Google Tasks row. Your browser opens Google sign-in. When you approve, every open task from all your task lists appears in Topics, including tasks assigned to you from Google Docs or Chat.

## Workspace admins

- `tasks.readonly` is a *sensitive* scope, not a restricted one. Internal apps are exempt from Google's verification.
- To allow the app for everyone, mark the client ID as **Trusted** under *Security → Access and data control → API controls → App access control*.
