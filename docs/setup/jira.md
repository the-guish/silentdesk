# Set up Jira access

Jira needs **no app registration**. Each user connects with their own token, entered in the app. SilentDesk checks the token, then keeps it in the OS keychain. It is never written to `.env` or to disk.

## Jira Cloud (`*.atlassian.net`)

1. Open https://id.atlassian.com/manage-profile/security/api-tokens.
2. Select **Create API token with scopes**. Scoped tokens are recommended because they can be read-only.
   - Name it "SilentDesk" and set an expiry; one year at most.
   - **App:** Jira.
   - **Scopes:** `read:jira-work` and `read:jira-user`. Nothing else is needed.
3. Copy the token. Atlassian shows it only once.
4. In SilentDesk, open **Topics**, select **Connect** on the Jira row, and fill in:
   - **Site:** `your-company.atlassian.net`;
   - **Email:** your Atlassian account email;
   - **API token:** the token you just created.

A token without scopes also works, but it can do anything your account can do in Jira. Prefer the scoped one.

## Jira Data Center / Server

1. In Jira, open your avatar → **Profile → Personal Access Tokens → Create token**, and set an expiry.
2. In SilentDesk, fill in:
   - **Site:** your Jira's address, e.g. `jira.company.com` or `https://company.com/jira`;
   - **Email:** leave it **empty**. An empty email tells SilentDesk this is a Data Center personal access token.
   - **API token:** the personal access token.

The site must use `https://`. SilentDesk refuses plain `http`, so tokens are never sent unencrypted.

## Disconnecting

**Disconnect** deletes the token from your keychain and all Jira data from SilentDesk. Jira does not let apps revoke API tokens, so also revoke it where you created it:
- **Cloud:** the Atlassian API tokens page above;
- **Data Center:** *Profile → Personal Access Tokens*.

## Admins

- **Jira Cloud:** organization admins can control whether users may create API tokens in Atlassian Administration, under the security settings for API tokens.
- **Data Center:** admins can limit personal access tokens, for example by setting a maximum expiry.
