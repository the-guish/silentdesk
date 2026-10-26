# Set up Slack access

SilentDesk connects to Slack through a Slack app that **you or your organization creates**. The app only needs a **client ID**: it is a desktop app using PKCE, so there is no client secret.

## 1. Create the Slack app

1. Go to https://api.slack.com/apps and select **Create New App → From a manifest**.
2. Pick your workspace.
3. Paste the contents of [`slack-app-manifest.json`](slack-app-manifest.json) and create the app. The manifest sets everything up:
   - **Redirect URL:** `http://localhost:47615/slack/callback`.
   - **User token scopes:** `search:read`, `users:read`, and read access to every conversation you can see. That is direct messages (`im:read`, `im:history`, `mpim:read`, `mpim:history`) and channels, public and private (`channels:read`, `channels:history`, `groups:read`, `groups:history`). There are no bot scopes, so the app cannot post or change anything.
   - **PKCE enabled:** this makes the app a *public client*, so no client secret is used. Slack does not let you turn PKCE off again without contacting their support, which is fine for a desktop-only app.
   - **Token rotation:** access tokens last 12 hours and are renewed automatically. If SilentDesk is not used for 30 days, you will need to connect again.
4. On **Basic Information**, copy the **Client ID**.

To set it up by hand instead, use the same values under *OAuth & Permissions*.

## 2. Give the client ID to SilentDesk

```sh
cp .env.example .env     # if you don't have one yet
# edit .env:
#   SILENTDESK_SLACK_CLIENT_ID=1234567890.0987654321
linux/gtk/run.sh
```

**If port 47615 is taken** on your machine, pick another free port and use it in both places:
- in `.env`: `SILENTDESK_SLACK_REDIRECT_PORT=<port>`;
- in the Slack app: the redirect URL `http://localhost:<port>/slack/callback`.

## 3. Connect

Open **Topics** and select **Connect** on the Slack row. Your browser opens Slack's approval page. When you allow it, SilentDesk pulls your last 10 direct messages.

## Workspace admins

- If your workspace requires approval for apps, members will see "request to install". Approve the SilentDesk app under *Manage apps*.
- Each organization creates its own app. There is no shared SilentDesk app or server.
