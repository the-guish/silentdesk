"""The filter bar's state: the values each filter offers and has chosen, its
labels, and the query it makes for the core. Pure, so it is tested without a
display. See spec/filters.md."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from silentdesk.contract import DEFAULT_PROJECT, Project, ServiceStatus, TopicQuery, TopicView

from .format import service_name


@dataclass(frozen=True)
class Choice:
    """One value a filter offers: what the query gets, and what the user reads."""

    value: str
    label: str


@dataclass(frozen=True)
class Field:
    key: str
    title: str
    # Always in the bar, or added with the + button.
    always: bool


PROJECT = Field("projects", "Project", always=True)
SERVICE = Field("services", "Service", always=True)
PEOPLE = Field("people", "People", always=False)
WAITING_ON = Field("waiting_on", "Waiting on", always=False)
DELETABLE = Field("deletable", "Deletable", always=False)
UPDATED = Field("updated", "Updated", always=False)

# In the order the + button lists them; the bar shows them as added.
FIELDS = [PROJECT, SERVICE, PEOPLE, WAITING_ON, UPDATED, DELETABLE]
MORE = [field for field in FIELDS if not field.always]

WAITING_ON_CHOICES = [Choice("me", "Me"), Choice("others", "Others")]
DELETABLE_CHOICES = [Choice("yes", "Yes"), Choice("no", "No")]


def project_choices(projects: Iterable[Project]) -> list[Choice]:
    """Default first, then the projects by name, ignoring case."""
    ordered = sorted(projects, key=lambda project: (project.name.casefold(), project.id))
    return [Choice(DEFAULT_PROJECT, "Default"), *(Choice(project.id, project.name) for project in ordered)]


def service_choices(statuses: Iterable[ServiceStatus]) -> list[Choice]:
    """The connected services, by the names people know them by."""
    choices = [Choice(status.service, service_name(status.service)) for status in statuses if status.connected]
    return sorted(choices, key=lambda choice: choice.label)


def people_choices(topics: Iterable[TopicView]) -> list[Choice]:
    """Every author of an item, by name, ignoring case."""
    people = {item.author for topic in topics for item in topic.items if item.author}
    return [Choice(person, person) for person in sorted(people, key=lambda person: (person.casefold(), person))]


def toggle(chosen: frozenset[str], value: str | None) -> frozenset[str]:
    """The values chosen after the user clicks `value`, or All for None. No
    value chosen is All."""
    if value is None:
        return frozenset()
    return chosen - {value} if value in chosen else chosen | {value}


def keep_offered(chosen: frozenset[str], choices: Iterable[Choice]) -> frozenset[str]:
    """Drops the values a filter no longer offers, such as a deleted project."""
    return chosen & {choice.value for choice in choices}


def label(title: str, chosen: frozenset[str], choices: Iterable[Choice]) -> str:
    """Such as "Project: All", "Project: Acme" or "Project: Acme +2"."""
    names = [choice.label for choice in choices if choice.value in chosen]
    if not names:
        return f"{title}: All"
    more = f" +{len(names) - 1}" if len(names) > 1 else ""
    return f"{title}: {names[0]}{more}"


@dataclass(frozen=True)
class Updated:
    """The Updated filter's range, in one of the forms Jira offers."""

    # "within": the last `amount` units. "over": more than `amount` units
    # ago. "between": from `first` to `last`, both days included.
    form: str
    amount: int = 7
    # "days" or "weeks".
    unit: str = "days"
    first: date | None = None
    last: date | None = None


def updated_range(updated: Updated | None, now: datetime) -> tuple[str | None, str | None]:
    """The query's updatedFrom and updatedTo, in UTC, for days in `now`'s
    time zone."""
    if updated is None:
        return None, None
    if updated.form in ("within", "over"):
        span = timedelta(**{updated.unit: updated.amount})
        moment = _rfc3339(now - span)
        return (moment, None) if updated.form == "within" else (None, moment)
    start = _rfc3339(datetime.combine(updated.first, time(), now.tzinfo)) if updated.first else None
    end = _rfc3339(datetime.combine(updated.last + timedelta(days=1), time(), now.tzinfo)) if updated.last else None
    return start, end


def updated_label(updated: Updated | None) -> str:
    """Such as "Updated: Last 7 days", "Updated: Over 2 weeks ago" or
    "Updated: Oct 1 – Oct 24"."""
    if updated is None:
        return "Updated: All"
    unit = updated.unit if updated.amount != 1 else updated.unit.removesuffix("s")
    if updated.form == "within":
        return f"Updated: Last {updated.amount} {unit}"
    if updated.form == "over":
        return f"Updated: Over {updated.amount} {unit} ago"
    days = [f"{day.strftime('%b')} {day.day}" if day else "…" for day in (updated.first, updated.last)]
    return f"Updated: {days[0]} – {days[1]}"


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def query(
    text: str, chosen: Mapping[str, frozenset[str]], updated: tuple[str | None, str | None] = (None, None)
) -> TopicQuery:
    """The core's query for the search text and the bar's choices."""
    deletable = chosen.get(DELETABLE.key, frozenset())
    return TopicQuery(
        text=text,
        projects=chosen.get(PROJECT.key, frozenset()),
        services=chosen.get(SERVICE.key, frozenset()),
        people=chosen.get(PEOPLE.key, frozenset()),
        waiting_on=chosen.get(WAITING_ON.key, frozenset()),
        updated_from=updated[0],
        updated_to=updated[1],
        # Yes and No together let every topic through, as All does.
        deletable=None if len(deletable) != 1 else "yes" in deletable,
    )


def project_name(projects: Iterable[Project], project_id: str | None) -> str:
    """A topic's project as the user reads it: Default for None."""
    return next((project.name for project in projects if project.id == project_id), "Default")


def new_project_name(typed: str, projects: Iterable[Project]) -> str | None:
    """The project the picker offers to create from what the user typed, or
    None when no project could take that name."""
    name = typed.strip()
    taken = {"all", "default", *(project.name.casefold() for project in projects)}
    return name if name and name.casefold() not in taken else None
