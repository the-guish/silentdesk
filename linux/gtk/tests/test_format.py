"""How topics read on screen."""

from datetime import UTC, datetime, timedelta, timezone

from silentdesk.contract import Direction, Item, TopicView

from silentdesk_gtk import format

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def topic(
    service: str = "gmail", direction: Direction | None = Direction.INBOUND, author: str | None = "Bo Lind"
) -> TopicView:
    items = [Item("m1", direction, author, None, "2026-10-24T09:00:00Z")]
    return TopicView("id-1", service, "Invoice for October", items, "2026-10-24T09:00:00Z")


def test_ago_reads_like_the_legacy_footer():
    assert format.ago(None, NOW) == "just now"
    assert format.ago("2026-10-24T11:59:30Z", NOW) == "just now"
    assert format.ago("2026-10-24T11:57:00Z", NOW) == "3 min ago"
    assert format.ago("2026-10-24T09:00:00Z", NOW) == "3 h ago"
    assert format.ago("2026-10-20T12:00:00Z", NOW) == "4 days ago"


def test_dates_show_the_time_today_the_day_this_year_or_the_full_date():
    local = NOW.astimezone(timezone(timedelta(hours=2)))
    assert format.short_date("2026-10-24T09:05:00Z", local) == "11:05"
    assert format.short_date("2026-03-02T09:00:00Z", local) == "Mar 2"
    assert format.short_date("2025-12-31T09:00:00Z", local) == "Dec 31, 2025"
    assert format.short_date("", local) == ""


def test_rows_name_the_service_and_who_wrote_last():
    assert format.subtitle(topic()) == "Gmail · Bo Lind"
    assert format.subtitle(topic("tasks", None, None)) == "Google Tasks"
    assert format.direction_icon(topic()) == "mail-unread-symbolic"
    assert format.direction_icon(topic(direction=Direction.OUTBOUND)) == "mail-send-symbolic"
    assert format.direction_icon(topic("tasks", None)) == "object-select-symbolic"


def test_search_matches_every_word_in_title_service_and_people():
    assert format.matches(topic(), "invoice bo")
    assert format.matches(topic(), "GMAIL")
    assert not format.matches(topic(), "invoice cy")
    assert format.matches(topic(), "")


def test_errors_read_as_one_line():
    from silentdesk.contract import RemoteError

    assert format.describe(RemoteError("jira", "Jira answered 503.")) == "Jira: Jira answered 503."
    assert format.describe(ValueError("Bad.")) == "Bad."
