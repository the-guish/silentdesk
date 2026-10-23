# Set up Gmail access

SilentDesk connects to Gmail through an OAuth client that **your organization owns**. You create it once in Google Cloud, then give its ID to SilentDesk.

## 1. Create the OAuth client

In the [Google Cloud console](https://console.cloud.google.com/):

1. **Create or pick a project.**
2. **Enable the Gmail API.** Go to *APIs & Services → Library*, search for "Gmail API", and select **Enable**.
3. **Configure the consent screen** under *Google Auth Platform* (shown as *OAuth consent screen* in older consoles):
   - **Audience:**
     - Choose **Internal** if you use Google Workspace. Only people in your organization can sign in, and Google does not need to review the app.
     - Otherwise choose **External** and add your account under **Test users**. In testing mode, Google expires refresh tokens after 7 days, so you will need to connect again weekly.
   - **Data access:** add the scope `https://www.googleapis.com/auth/gmail.metadata`.
4. **Create the client.** Go to *Clients → Create client*, choose application type **Desktop app**, and name it "SilentDesk".
5. **Copy the Client ID and Client secret.** For a desktop app, Google does not treat the secret as confidential.

## 2. Give the client to SilentDesk

For development, set the variables when you start the app:

```sh
export SILENTDESK_GOOGLE_CLIENT_ID="1234-abc.apps.googleusercontent.com"
export SILENTDESK_GOOGLE_CLIENT_SECRET="GOCSPX-..."
pnpm tauri dev
```

For a build you distribute inside your organization, set the same variables when you run `pnpm tauri build`. They are compiled into the app. Runtime values still take precedence.

## 3. Connect

Open **Topics** and select **Connect Gmail**. Your browser opens Google sign-in. When you approve, SilentDesk pulls your last 10 emails.

## Workspace admins

- To allow the app for everyone, open the Admin console, go to *Security → Access and data control → API controls → App access control*, and mark the client ID as **Trusted**.
- The `gmail.metadata` scope is a restricted scope. Internal apps are exempt from Google's verification. An External app published to production needs Google's verification and security assessment.
