from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.tasks import GoogleTask


@dataclass(frozen=True)
class TaskList:
    list_id: str
    title: str


class TasksApi(ABC):
    """The Google Tasks REST API. Every call takes a current access token."""

    @abstractmethod
    async def lists(self, token: str) -> list[TaskList]: ...

    @abstractmethod
    async def tasks(self, token: str, task_list: TaskList) -> list[GoogleTask]: ...
