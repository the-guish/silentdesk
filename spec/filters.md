# SilentDesk — Filters

Both apps show a filter bar over the topic queue, modelled on Jira's basic search. Each filter narrows the queue by one field of a topic. The core does the matching. The app sends the search text and the bar's choices as the query of `topics` ([cli.md](cli.md#topics)), and shows the topics it lists.

```
[ Project: All ▾ ] [ Service: All ▾ ] [ People: Bo ▾ ]                    [ + ]
```

Advanced search, with a query language like Jira's JQL, is not planned.

## The bar

- **Place:** the filter bar sits under the header on the queue, and is always shown. The search bar opens above it, as before.
- **Order:** Project comes first, then Service. Filters the user adds follow, in the order they were added. The `+` button is at the right end.
- **Label:** each filter is a button that names its field and its value, such as `Project: All`. With several values, it shows the first and a count of the rest: `Project: Acme +2`.
- **Choosing values:** a filter's button opens a list of its values with check boxes. A search entry above the list narrows it by name.
- **All:** every choice filter offers `All` first. All means the filter lets every topic through. Checking a value clears All. Clearing the last value checks All again.
- **Lifetime:** the bar keeps its choices while the app runs. The app starts with Project and Service on All, and no added filters.

## How filters combine

A topic shows when it matches the search and every filter. A choice filter with several values matches a topic that has any of them. A filter on All matches every topic, and stays out of the query.

When nothing matches, the queue says "No topics match your search and filters". A **Clear Filters** button there sets Project and Service to All and removes the added filters. The search text stays.

## Project

Project is always in the bar. Its values are:

1. `All`: every topic.
2. `Default`: every topic without a project. The query names it `default`.
3. The user's projects, sorted by name, ignoring case.

Project names are free text, such as `Project-X` or `Project-45`. The core keeps the projects; see `projects` in [cli.md](cli.md#projects). A project the user deletes leaves the filter. Its topics are then in Default.

## Service

Service is always in the bar. Its values are `All`, then every connected service by its display name, sorted by name: `GitHub`, `Gmail`, `Google Tasks`. A service that disconnects leaves the filter.

## More filters

The `+` button at the right of the bar opens a list of the other fields, with a check box and a search entry, as Jira's **More** does. Checking a field adds its filter to the bar and opens it. Unchecking it removes the filter and its condition. A filter's own list also ends with **Remove Filter**.

Each field is a field of the topic, or computed from its items. The query field in [cli.md](cli.md#topics) says how it matches.

| Field | Kind | Values | Query field |
|-------|------|--------|-------------|
| People | choice | Every author of an item, over the whole queue, sorted by name | `people` |
| Waiting on | choice | `Me`, `Others` | `waitingOn` |
| Updated | date | A range | `updatedFrom`, `updatedTo` |
| Deletable | choice | `Yes`, `No` | `deletable` |

A date filter offers three forms, as Jira's do. The app turns each into times, in the user's time zone.

| Form | Query |
|------|-------|
| **Within the last** N days or weeks | `updatedFrom` is that long before now. |
| **More than** N days or weeks ago | `updatedTo` is that long before now. |
| **Between** two dates, both included | `updatedFrom` is the start of the first day. `updatedTo` is the start of the day after the second. |

It reads `Updated: All` until the user sets a range.

A new filter needs a new query field in the core first.

## Moving topics between projects

The topic screen shows the topic's project as a button in its header, such as `Project: Default`. The button opens the list of projects, with Default first and a search entry. Choosing one moves the topic there (`move` in [cli.md](cli.md#move-topic-id-project-id)).

When the search text names no project, the list offers **New Project "…"**. It creates the project with that name and moves the topic to it.

The main menu holds **Projects**, a dialog that lists the projects. There the user can rename and delete them.

## Planned

- Rules that put new topics in a project. Until then, every new topic starts in Default.
- Moving several topics at once from the queue.
- Keeping the bar's choices when the app restarts.
