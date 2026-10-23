# Set up GitHub access

GitHub needs **no app registration**. Each user connects with their own personal access token, entered in the app. SilentDesk checks the token, then keeps it in the OS keychain. It is never written to `.env` or to disk.

## Recommended: a fine-grained, read-only token

1. On GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Set it up:
   - **Name:** "SilentDesk". **Expiration:** your choice; shorter is safer.
   - **Resource owner:** your organization, or yourself for personal repositories.
   - **Repository access:** *All repositories*, or only the ones you work in.
   - **Repository permissions:** **Pull requests: Read-only**. *Metadata: Read-only* is added automatically. Nothing else is needed.
3. Generate it and copy the token.
4. If your organization requires approval for fine-grained tokens, the token shows as *pending* until an organization owner approves it.

**One limit:** a fine-grained token covers **one** resource owner, meaning one organization or your personal account. Pull requests in other organizations won't appear.

## Alternative: a classic token, for several organizations

A classic token with the `repo` scope sees pull requests across all your organizations. But `repo` also grants write access, so prefer a fine-grained token when you work in a single organization. Organizations using SAML single sign-on require you to authorize the token for them (*Configure SSO* next to the token).

## Connect

In SilentDesk, open **Settings** (the gear button) and select **Connect** on the GitHub row, then fill in:
- **Server:** leave it empty for github.com. For GitHub Enterprise Server, enter your host, e.g. `github.acme.com`; it must use `https://`.
- **Token:** the token you created.

SilentDesk then pulls the open pull requests that:
- are waiting for your review (including review requests to your teams);
- are assigned to you;
- you opened.

## Disconnecting

**Disconnect** deletes the token from your keychain and all GitHub data from SilentDesk. GitHub does not let apps revoke personal access tokens, so also delete it under **Developer settings → Personal access tokens**.

## Admins

Organization owners can require approval for fine-grained tokens, limit their lifetime, or block classic tokens, under *Organization settings → Personal access tokens*.
