# SilentDesk — GitHub Integration

Status: v1 implemented · Last updated: 2026-10-23

## Goal (v1)

Let the user connect GitHub securely and pull their **open pull requests** as topics. One pull request maps to one topic. A pull request is included when it is:

| Reason | Direction | Search qualifier |
|--------|-----------|------------------|
| Waiting for the user's review, directly or through one of their teams | Inbound | `review-requested:@me` |
| Assigned to the user | Inbound | `assignee:@me` |
| Opened by the user | Outbound | `author:@me` |

When a pull request matches several of these, the first reason in the table wins.

## Why a token, not OAuth

- **OAuth apps:** reading private pull requests needs the classic `repo` scope, which also grants write access. That is no tighter than a token.
- **GitHub Apps:** they could be read-only, but each organization would have to install the app and the user would sign in through it. That brings back the registration step that Jira and GitHub otherwise avoid.

A personal access token instead:
- needs no registration, so an employee can set it up alone;
- can be **read-only**: a fine-grained token with *Pull requests: Read*;
- works the same way on **GitHub Enterprise Server**;
- is governed by the organization: owners can require approval, cap expiry, or block classic tokens.

The trade-off: a fine-grained token covers a single organization. Users across several organizations can use a classic token, and the setup guide explains the broader access it grants. A GitHub App with device flow remains an option if organizations want central control.

## Connecting

1. The user selects **Connect** on the GitHub row in Settings, and enters an optional server and a token.
2. **Server:**
   - empty or `github.com` → API at `https://api.github.com`;
   - any other host → GitHub Enterprise Server at `https://<host>/api/v3`;
   - plain `http` is refused.
3. **Check:** `GET /user`, with the token as a Bearer token and `X-GitHub-Api-Version: 2022-11-28`. A 401 means the token is rejected; a 404 means no GitHub API was found at that address.
4. **Storage:** the token goes into the OS credential store as `github-token`. The endpoint and login go into the encrypted vault. A first sync follows.
5. **On failure, nothing is stored.** The form clears the token on submit.

## Syncing

- **Automatic,** at startup, every 2 minutes and on window focus. See `docs/specs/sync.md`.
- **Fetching:** three `GET /search/issues` queries, each `is:pr is:open archived:false <qualifier>`, sorted by last update, 50 per query.
  - GitHub's search now rejects queries that do not name a type, so each one starts with `is:pr`.
  - Results are merged by pull request ID and sorted by last update.
- **Stored per pull request:** repository (`owner/name`), number, reason, direction, draft flag, author login, URL and last-updated date. The title becomes the topic title.
- **Not fetched:** descriptions, diffs, comments and reviews.
- **Re-sync:** a pull request already stored keeps its topic. Pull requests that are merged, closed, or no longer involve the user are removed with their topics. Other services' topics are untouched.
- **401 on sync:** the token is deleted and the user is asked to connect again. Topics stay.

## Disconnecting

**Disconnect** deletes the token and all local GitHub data. GitHub has no API for revoking a personal access token, so the setup guide tells the user where to delete it.

## Corporate deployment

- **Nothing to register,** and no `.env` setting.
- **Governance:** organization owners control personal access tokens: approval, maximum lifetime, and whether classic tokens are allowed. SAML SSO organizations require the token to be authorized for SSO.
- **Network.** HTTPS uses the OS TLS stack, trusted certificates and proxy settings. The only host contacted is `api.github.com` or the Enterprise Server host.

## Risks and next steps

- **Not yet tested against a real account.** This development sandbox's network proxy replaces GitHub credentials with its own and blocks `/search`, so connecting and syncing must be checked on a normal machine.
- **Search rate limit:** 30 requests per minute for authenticated users. A sync uses 3.
- **Next:**
  - show review state and checks (needs a per-PR call);
  - open a pull request in the browser from its URL;
  - link a pull request to the Jira issue its title or branch names (e.g. `PAY-412`).
