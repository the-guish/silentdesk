"""Rules about Google Tasks. See legacy/docs/specs/integrations/google-tasks.md."""

from __future__ import annotations

from ....contract import Item, Topic
from ..domain.tasks import GoogleTask

SERVICE = "tasks"
TASKS_READONLY = "https://www.googleapis.com/auth/tasks.readonly"
# Read-only access to task lists and tasks. `openid email` only names the account.
SCOPES = (TASKS_READONLY, "openid", "email")
REQUIRED_SCOPES = (TASKS_READONLY,)


def is_open(task: GoogleTask) -> bool:
    return not task.completed and not task.deleted


def topic(task: GoogleTask) -> Topic:
    """One topic per task, with the task as its one item."""
    # SilentDesk has read-only access to Google Tasks.
    item = Item(key=task.task_id, direction=None, author=None, url=task.url, date=task.updated, deletable=False)
    return Topic(key=task.task_id, title=task.title.strip() or "Untitled task", items=[item], deletable=False)
