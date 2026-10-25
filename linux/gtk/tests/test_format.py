"""How topics read on screen."""

from datetime import UTC, datetime, timedelta, timezone

from silentdesk.contract import Direction, Item, TopicView

from silentdesk_gtk import format

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def topic(
    service: str = "gmail", direction: Direction | None = Direction.INBOUND, author: str | None = "Bo Lind"
) -> TopicView:
    items = [Item("m1", direction, author, None, "2026-10-24T09:00:00Z", False)]
    return TopicView("id-1", service, "Invoice for October", items, "2026-10-24T09:00:00Z", False)


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
    assert format.subtitle(topic(direction=Direction.OUTBOUND)) == "Gmail · Waiting on others"


def test_avatars_show_who_wrote_last_or_an_icon():
    assert format.avatar(topic()) == ("Bo Lind", "avatar-default-symbolic")
    assert format.avatar(topic("tasks", None, None)) == (None, "checkbox-checked-symbolic")


def test_items_say_whether_they_were_received_or_sent_and_when():
    local = NOW.astimezone(timezone(timedelta(hours=2)))
    assert format.item_line(Direction.INBOUND, "2026-10-24T09:05:00Z", local) == "Received · Today 11:05"
    assert format.item_line(Direction.OUTBOUND, "2026-03-02T09:00:00Z", local) == "Sent · Mar 2, 11:00"
    assert format.item_line(None, "2025-12-31T09:00:00Z", local) == "Dec 31, 2025, 11:00"


def test_errors_read_as_one_line():
    from silentdesk.contract import AuthError, RemoteError, SyncFailed

    assert format.describe(RemoteError("jira", "Jira answered 503.")) == "Jira: Jira answered 503."
    assert format.describe(ValueError("Bad.")) == "Bad."
    failed = SyncFailed([("tasks", AuthError("tasks", "Not configured.")), ("gmail", RemoteError("gmail", "Quota."))])
    assert format.describe(failed) == "Could not sync Google Tasks: Not configured. Could not sync Gmail: Quota."
