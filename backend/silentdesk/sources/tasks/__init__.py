"""Google Tasks: every open task as a topic of its own, read-only. Signs in
with the same Google OAuth client as Gmail, with its own grant and refresh
token. See docs/specs/integrations/google-tasks.md."""

from .service import TasksSource

__all__ = ["TasksSource"]
