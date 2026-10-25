"""The filter bar's state, without a display."""

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
