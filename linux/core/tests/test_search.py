"""Which topics a query lists: core.search, a pure function."""

from __future__ import annotations

from dataclasses import replace

import pytest

from silentdesk.apps.desk.core.search import check, matches
from silentdesk.apps.desk.domain.topics import TopicRecord
from silentdesk.contract import Direction, InvalidQuery, Item, StatusCategory, TopicQuery, TopicStatus

INVOICE = TopicRecord(
    "1",
    "gmail",
    "t1",
    "Invoice for October",
    [
        Item("m1", Direction.INBOUND, "Bo", None, "2026-10-20T09:00:00Z", True),
        Item("m2", Direction.OUTBOUND, "Ana", None, "2026-10-24T09:00:00Z", True),
    ],
    "2026-10-20T09:00:00Z",
    "2026-10-24T09:00:00Z",
    True,
)
TASK = TopicRecord(
    "2", "tasks", "k2", "Renew passport", [Item("k2", None, None, None, "2026-10-01T00:00:00Z", False)],
    "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z", False,
)  # fmt: skip


@pytest.mark.parametrize(
    ("record", "deletable", "query", "expected"),
    [
        (INVOICE, True, TopicQuery(), True),
        (INVOICE, True, TopicQuery(text="invoice bo"), True),
        (INVOICE, True, TopicQuery(text="GMAIL"), True),
        (INVOICE, True, TopicQuery(text="m2"), True),
        (INVOICE, True, TopicQuery(text="invoice cy"), False),
        (
            replace(INVOICE, status=TopicStatus("Code Review", StatusCategory.IN_PROGRESS)),
            True,
            TopicQuery(text="review"),
            True,
        ),
        (INVOICE, True, TopicQuery(text="review"), False),
        (TASK, False, TopicQuery(text="google tasks"), True),
        (INVOICE, True, TopicQuery(services=frozenset({"gmail", "github"})), True),
        (TASK, False, TopicQuery(services=frozenset({"gmail"})), False),
        (INVOICE, True, TopicQuery(people=frozenset({"Bo"})), True),
        (INVOICE, True, TopicQuery(people=frozenset({"Cy"})), False),
        (TASK, False, TopicQuery(people=frozenset({"Bo"})), False),
        (INVOICE, True, TopicQuery(waiting_on=frozenset({"others"})), True),
        (INVOICE, True, TopicQuery(waiting_on=frozenset({"me"})), False),
        (TASK, False, TopicQuery(waiting_on=frozenset({"me"})), True),
        (INVOICE, True, TopicQuery(updated_from="2026-10-24T09:00:00Z"), True),
        (INVOICE, True, TopicQuery(updated_from="2026-10-24T09:00:01Z"), False),
        (INVOICE, True, TopicQuery(updated_to="2026-10-24T09:00:00Z"), False),
        (INVOICE, True, TopicQuery(updated_to="2026-10-25T00:00:00Z"), True),
        (INVOICE, True, TopicQuery(updated_from="2026-10-24T06:00:00-03:00"), True),
        (INVOICE, True, TopicQuery(updated_to="2026-10-24T06:00:00-03:00"), False),
        (INVOICE, True, TopicQuery(projects=frozenset({"default"})), True),
        (INVOICE, True, TopicQuery(projects=frozenset({"p1"})), False),
        (replace(INVOICE, project_id="p1"), True, TopicQuery(projects=frozenset({"p1", "p2"})), True),
        (replace(INVOICE, project_id="p1"), True, TopicQuery(projects=frozenset({"default"})), False),
        (INVOICE, True, TopicQuery(deletable=True), True),
        (TASK, False, TopicQuery(deletable=True), False),
        (TASK, False, TopicQuery(deletable=False), True),
        (INVOICE, True, TopicQuery(text="invoice", services=frozenset({"gmail"}), people=frozenset({"Ana"})), True),
        (INVOICE, True, TopicQuery(text="invoice", services=frozenset({"tasks"})), False),
    ],
)
def test_a_topic_matches_the_search_and_every_filter(record, deletable, query, expected):
    assert matches(record, deletable, query) is expected


@pytest.mark.parametrize("bound", ["yesterday", "2026-10-24", "2026-10-24T09:00:00", "2026-10-24 09:00:00Z"])
def test_a_bound_that_is_not_rfc_3339_is_refused(bound):
    with pytest.raises(InvalidQuery):
        check(TopicQuery(updated_from=bound))
