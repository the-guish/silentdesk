# SilentDesk — GitHub status

A pull request has a status given by GitHub. SilentDesk shows it in the topic's chip, as [topic-status.md](../../topic-status.md) describes.

## The chip

A pull request shows one chip. The first row that applies wins.

| Order | Chip | When | Category |
|-------|------|------|----------|
| 1 | Merged | The pull request is merged. | `done` |
| 2 | Closed | The pull request is closed without a merge. | `done` |
| 3 | CI Failed | A check on its last commit failed. | `inProgress` |
| 4 | Approved | A reviewer approved it. | `inProgress` |
| 5 | Changes Requested | A reviewer asked for changes. | `inProgress` |
| 6 | Ready | It is ready for review. | `inProgress` |
| 7 | Draft | It is a draft. | `new` |

The order follows the pull request's life, from its end back to its start. Merged and Closed come first because they end it. CI Failed comes next because a failed check blocks a pull request at any stage.

## Where the status comes from

One GraphQL query per sync reads every pull request in the queue. It replaces the three searches.

| GraphQL field | Value | Chip |
|---------------|-------|------|
| `merged` | `true` | Merged |
| `state` | `CLOSED` | Closed |
| `commits(last: 1)` → `statusCheckRollup.state` | `FAILURE` or `ERROR` | CI Failed |
| `reviewDecision` | `APPROVED` | Approved |
| `reviewDecision` | `CHANGES_REQUESTED` | Changes Requested |
| `isDraft` | `false` | Ready |
| `isDraft` | `true` | Draft |

The query goes to `https://api.github.com/graphql`, or to `https://<host>/api/graphql` on GitHub Enterprise Server.

## Open points

- **Merged and Closed:** the queue lists open pull requests only. These two chips show once a pull request stays in the queue for a while after it ends. That needs its own rule.
- **Token:** a fine-grained token may need more read permissions to see checks. To check on a real account.
- **More signals:** a running or passed check could show as a small icon next to the date.
- **Open questions:** whether the comments hold an open question. SilentDesk would have to read the comments' text, which it does not do today. This needs a check against the [core principles](../../core.md) first.
