"""The filter bar's state, without a display."""

from datetime import date, datetime, timedelta, timezone

import pytest
from silentdesk.contract import Direction, Item, Project, ServiceStatus, TopicQuery, TopicView

from silentdesk_gtk import filters
from silentdesk_gtk.filters import Choice

ACME, BETA = Choice("p1", "Acme"), Choice("p2", "beta")


def by(*authors: str | None) -> TopicView:
    items = [
        Item(f"m{n}", Direction.INBOUND, author, None, "2026-10-24T09:00:00Z", False)
        for n, author in enumerate(authors)
    ]
    return TopicView("t", "gmail", "Thread", items, "2026-10-24T09:00:00Z", False)


def test_projects_start_with_default_then_go_by_name_ignoring_case():
    projects = [Project("p3", "Project-X"), Project("p2", "beta"), Project("p1", "Acme")]
    assert filters.project_choices(projects) == [Choice("default", "Default"), ACME, BETA, Choice("p3", "Project-X")]


def test_services_are_the_connected_ones_by_name():
    statuses = [
        ServiceStatus("tasks", True, True, "ana"),
        ServiceStatus("slack", False, False, None),
        ServiceStatus("gmail", True, True, "ana"),
        ServiceStatus("github", True, True, "ana"),
    ]
    assert [c.label for c in filters.service_choices(statuses)] == ["GitHub", "Gmail", "Google Tasks"]


def test_people_are_every_author_once_by_name_ignoring_case():
    choices = filters.people_choices([by("bo", "Ana", None), by("Ana", "Cy")])
    assert [c.value for c in choices] == ["Ana", "bo", "Cy"]


@pytest.mark.parametrize(
    ("chosen", "value", "expected"),
    [
        (set(), "p1", {"p1"}),
        ({"p1"}, "p2", {"p1", "p2"}),
        ({"p1", "p2"}, "p1", {"p2"}),
        ({"p1"}, "p1", set()),
        ({"p1", "p2"}, None, set()),
        (set(), None, set()),
    ],
)
def test_checking_a_value_clears_all_and_clearing_the_last_one_is_all(chosen, value, expected):
    assert filters.toggle(frozenset(chosen), value) == frozenset(expected)


def test_values_no_longer_offered_leave_the_filter():
    assert filters.keep_offered(frozenset({"p1", "gone"}), [ACME, BETA]) == {"p1"}


@pytest.mark.parametrize(
    ("chosen", "expected"),
    [
        (set(), "Project: All"),
        ({"p2"}, "Project: beta"),
        ({"p2", "p1"}, "Project: Acme +1"),
        ({"p1", "p2", "default"}, "Project: Default +2"),
    ],
)
def test_a_filter_names_its_first_value_and_counts_the_rest(chosen, expected):
    choices = [Choice("default", "Default"), ACME, BETA]
    assert filters.label("Project", frozenset(chosen), choices) == expected


@pytest.mark.parametrize(
    ("chosen", "expected"),
    [
        ({}, TopicQuery(text="inv")),
        (
            {"projects": {"default", "p1"}, "services": {"gmail"}},
            TopicQuery(text="inv", projects=frozenset({"default", "p1"}), services=frozenset({"gmail"})),
        ),
        (
            {"people": {"Bo"}, "waiting_on": {"others"}},
            TopicQuery(text="inv", people=frozenset({"Bo"}), waiting_on=frozenset({"others"})),
        ),
        ({"deletable": {"yes"}}, TopicQuery(text="inv", deletable=True)),
        ({"deletable": {"no"}}, TopicQuery(text="inv", deletable=False)),
        ({"deletable": {"yes", "no"}}, TopicQuery(text="inv")),
    ],
)
def test_the_bar_makes_the_cores_query(chosen, expected):
    assert filters.query("inv", {key: frozenset(values) for key, values in chosen.items()}) == expected


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("  Gamma ", "Gamma"), ("", None), ("   ", None), ("acme", None), ("ALL", None), ("default", None)],
)
def test_the_picker_offers_a_new_project_only_for_a_free_name(typed, expected):
    assert filters.new_project_name(typed, [Project("p1", "Acme")]) == expected


def test_a_topic_without_a_project_is_in_default():
    projects = [Project("p1", "Acme")]
    assert filters.project_name(projects, "p1") == "Acme"
    assert filters.project_name(projects, None) == "Default"


# Noon on Oct 24 in Buenos Aires, 15:00 UTC.
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone(timedelta(hours=-3)))


@pytest.mark.parametrize(
    ("updated", "expected"),
    [
        (None, (None, None)),
        (filters.Updated("within", 7, "days"), ("2026-10-17T15:00:00Z", None)),
        (filters.Updated("within", 2, "weeks"), ("2026-10-10T15:00:00Z", None)),
        (filters.Updated("over", 30, "days"), (None, "2026-09-24T15:00:00Z")),
        (
            filters.Updated("between", first=date(2026, 10, 1), last=date(2026, 10, 24)),
            ("2026-10-01T03:00:00Z", "2026-10-25T03:00:00Z"),
        ),
        (filters.Updated("between", first=date(2026, 10, 1)), ("2026-10-01T03:00:00Z", None)),
    ],
)
def test_the_updated_filter_becomes_times_in_utc_for_the_users_days(updated, expected):
    assert filters.updated_range(updated, NOW) == expected


@pytest.mark.parametrize(
    ("updated", "expected"),
    [
        (None, "Updated: All"),
        (filters.Updated("within", 7, "days"), "Updated: Last 7 days"),
        (filters.Updated("within", 1, "weeks"), "Updated: Last 1 week"),
        (filters.Updated("over", 2, "weeks"), "Updated: Over 2 weeks ago"),
        (filters.Updated("between", first=date(2026, 10, 1), last=date(2026, 10, 24)), "Updated: Oct 1 – Oct 24"),
    ],
)
def test_the_updated_filter_names_its_range(updated, expected):
    assert filters.updated_label(updated) == expected


def test_the_updated_range_goes_into_the_query():
    query = filters.query("", {}, ("2026-10-17T15:00:00Z", None))
    assert query == TopicQuery(updated_from="2026-10-17T15:00:00Z")
