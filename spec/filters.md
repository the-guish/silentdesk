# SilentDesk — Filters

Both apps show a filter bar over the topic queue, modelled on Jira's basic search. Each filter narrows the queue by one field of a topic. The cores only list the data: each app filters the topics in memory, as it does for search.

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

A topic shows when it matches the search and every filter. A choice filter with several values matches a topic that has any of them. A filter on All matches every topic.

When nothing matches, the queue says "No topics match your search and filters". A **Clear Filters** button there sets Project and Service to All and removes the added filters. The search text stays.

## Project

Project is always in the bar. Its values are:

1. `All`: every topic.
2. `Default`: every topic without a project, where `projectId` is null.
3. The user's projects, sorted by name, ignoring case.

Project names are free text, such as `Project-X` or `Project-45`. The core keeps the projects; see `projects` in [cli.md](cli.md#projects). A project the user deletes leaves the filter. Its topics are then in Default.

## Service

Service is always in the bar. Its values are `All`, then every connected service by its display name, sorted by name: `GitHub`, `Gmail`, `Google Tasks`. A service that disconnects leaves the filter.

## More filters

The `+` button at the right of the bar opens a list of the other fields, with a check box and a search entry, as Jira's **More** does. Checking a field adds its filter to the bar and opens it. Unchecking it removes the filter and its condition. A filter's own list also ends with **Remove Filter**.

Every field is a field of the topic as `topics` lists it ([cli.md](cli.md#topics)). Some are computed from the topic's items.

| Field | Kind | Matches | Computed from |
|-------|------|---------|---------------|
| People | choice | Topics where any chosen person wrote an item | `items[].author`, over every topic in the queue |
| Waiting on | choice: `Me`, `Others` | `Others`: the newest item is outbound. `Me`: any other topic. | The newest item's `direction` |
| Updated | date | Topics whose `updatedAt` falls in the range | `updatedAt` |
| Deletable | choice: `Yes`, `No` | Topics whose `deletable` is that value | `deletable` |

A date filter offers three forms, as Jira's do:

- **Within the last** a number of days or weeks.
- **More than** a number of days or weeks ago.
- **Between** two dates, both included.

It reads `Updated: All` until the user sets a range. Dates are in the user's time zone.

A new field joins this table when the core adds it to `topics`, or when an app can compute it from the fields there.

## Moving topics between projects

The topic screen shows the topic's project as a button in its header, such as `Project: Default`. The button opens the list of projects, with Default first and a search entry. Choosing one moves the topic there (`move` in [cli.md](cli.md#move-topic-id-project-id)).

When the search text names no project, the list offers **New Project "…"**. It creates the project with that name and moves the topic to it.

The main menu holds **Projects**, a dialog that lists the projects. There the user can rename and delete them.

## Planned

- Rules that put new topics in a project. Until then, every new topic starts in Default.
- Moving several topics at once from the queue.
- Keeping the bar's choices when the app restarts.
