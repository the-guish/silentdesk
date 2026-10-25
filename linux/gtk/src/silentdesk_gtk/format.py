"""How topics read on screen: service names, dates and search text. Pure,
so it is tested without a display."""

from __future__ import annotations

from datetime import datetime

from silentdesk.contract import ConnectorError, Direction, SyncFailed, TopicView

SERVICE_NAMES = {"gmail": "Gmail", "github": "GitHub", "jira": "Jira", "slack": "Slack", "tasks": "Google Tasks"}


def service_name(service: str) -> str:
    return SERVICE_NAMES.get(service, service.title())


def parse(rfc3339: str | None) -> datetime | None:
    try:
        moment = datetime.fromisoformat(rfc3339 or "")
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def ago(rfc3339: str | None, now: datetime) -> str:
    """Such as "just now", "3 min ago" or "2 h ago", for the footer."""
    moment = parse(rfc3339)
    if moment is None:
        return "just now"
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // (24 * 60)} days ago"


def short_date(rfc3339: str | None, now: datetime) -> str:
    """A topic's date in local time: the time today, the day this year, or
    the full date."""
    moment = parse(rfc3339)
    if moment is None:
        return ""
    local, today = moment.astimezone(now.tzinfo), now
    if local.date() == today.date():
        return local.strftime("%H:%M")
    if local.year == today.year:
        return f"{local.strftime('%b')} {local.day}"
    return f"{local.strftime('%b')} {local.day}, {local.year}"


def subtitle(topic: TopicView) -> str:
    """The service, then who the user is dealing with: who wrote the newest
    item, or that it waits on others when the user wrote it."""
    newest = topic.items[-1] if topic.items else None
    if newest is not None and newest.direction == Direction.OUTBOUND:
        return f"{service_name(topic.service)} · Waiting on others"
    authors = [item.author for item in topic.items if item.author]
    return " · ".join([service_name(topic.service), *authors[-1:]])


def avatar(topic: TopicView) -> tuple[str | None, str]:
    """What the row's avatar shows: whose initials, from the newest item
    with an author, and the icon used without them."""
    author = next((item.author for item in reversed(topic.items) if item.author), None)
    return author, "checkbox-checked-symbolic" if topic.service == "tasks" else "avatar-default-symbolic"


def long_date(rfc3339: str | None, now: datetime) -> str:
    """An item's date in local time with the time of day: "Today 09:12",
    "Oct 24, 09:12", or with the year when it is not this one."""
    moment = parse(rfc3339)
    if moment is None:
        return ""
    local = moment.astimezone(now.tzinfo)
    time = local.strftime("%H:%M")
    if local.date() == now.date():
        return f"Today {time}"
    day = f"{local.strftime('%b')} {local.day}"
    return f"{day}, {time}" if local.year == now.year else f"{day}, {local.year}, {time}"


def item_line(direction: Direction | None, date: str, now: datetime) -> str:
    """Under an item's author: whether the user received or sent it, and when."""
    when = long_date(date, now)
    if direction == Direction.OUTBOUND:
        return f"Sent · {when}"
    if direction == Direction.INBOUND:
        return f"Received · {when}"
    return when


def search_text(topic: TopicView) -> str:
    """Everything a search matches against, lowercased."""
    parts = [topic.title, service_name(topic.service)]
    parts += [part for item in topic.items for part in (item.author, item.key) if part]
    return "\n".join(parts).lower()


def matches(topic: TopicView, query: str) -> bool:
    """Whether every word of the query is in the topic."""
    text = search_text(topic)
    return all(word in text for word in query.lower().split())


def describe(error: BaseException) -> str:
    """An error as one line for a toast."""
    if isinstance(error, SyncFailed):
        return " ".join(
            f"Could not sync {service_name(service)}: {failure or type(failure).__name__}"
            for service, failure in error.failures
        )
    if isinstance(error, ConnectorError) and error.service:
        return f"{service_name(error.service)}: {error}"
    return str(error) or type(error).__name__
