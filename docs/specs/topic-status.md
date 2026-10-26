# SilentDesk — Topic status

A topic has a status given by its service, such as `In Progress` for a Jira issue. Both apps show it as a chip, first in every row of the queue.

## Which services report one

| Service | Status |
|---------|--------|
| Jira | The issue's status: its name and its category. |
| GitHub, Gmail, Google Tasks, Slack | None. |

A connector that gains a status later reports it the same way, and the apps show it with no change.

## The status

A status has a name and a category.

- **Name:** the service's own words, such as `Code Review`. Each Jira workflow names its statuses as it likes.
- **Category:** where the status stands, the same for every service. The apps colour the chip by it.

| Category | Meaning | From Jira's `statusCategory.key` |
|----------|---------|----------------------------------|
| `new` | Not started | `new` |
| `inProgress` | Started | `indeterminate` |
| `done` | Finished | `done` |

Any other Jira category gives a status with a null category.

The service owns the status. Each sync stores the status the connector reports, and a topic whose service reports none has none. `topics` prints it as `status` ([cli.md](cli.md#topics)).

The search matches the status's name, as it matches the title and the people.

## The chip

Every row of the queue starts with a chip, left of the avatar. The chip names the topic's status, or shows a dash when the topic has none.

```
[ In Progress ] (A) Fix the login timeout                 09:12
[ Code Review ] (B) Add the export button                  Oct 24
[      —      ] (C) Invoice for October                    Oct 23
```

- **Look:** the name in small text, inside a rounded chip, coloured by the category: grey for `new`, blue for `inProgress`, green for `done`. A null category is grey.
- **No status:** a topic without one gets a fainter grey chip with a dash, `—`.
- **Action:** none yet. A click on the chip opens the topic, as a click elsewhere on the row does.
- **Width:** every chip in the queue has the same width, so every title starts at the same place. The width fits the widest name among all the topics, shown or not, and at least the dash. It is at most a quarter of the queue's width. A longer name ends with an ellipsis, and its tooltip shows it whole.
- **Resizing:** the width is worked out again on each refresh, and when the queue's width changes.

## Planned

- A Status filter in the filter bar, with a `status` query field.
- Acting on the chip, such as moving a Jira issue to another status.
- The chip in the macOS app.
