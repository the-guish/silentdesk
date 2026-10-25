from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.tasks import GoogleTask, TaskList


class TasksApi(ABC):
    """The Google Tasks REST API, read-only. Every call takes a current access token."""

    @abstractmethod
    async def email(self, token: str) -> str:
        """The signed-in account's email address."""

    @abstractmethod
    async def lists(self, token: str) -> list[TaskList]: ...

    @abstractmethod
    async def tasks(self, token: str, task_list: TaskList) -> list[GoogleTask]:
        """Every task in the list Google returns: open ones, and any it still
        reports as completed or deleted."""
