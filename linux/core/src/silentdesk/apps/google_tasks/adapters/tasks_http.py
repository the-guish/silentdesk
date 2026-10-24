from __future__ import annotations

from ....contract import Http
from ..domain.tasks import GoogleTask
from ..ports.tasks_api import TaskList, TasksApi


class TasksHttpApi(TasksApi):
    def __init__(self, http: Http, base_url: str) -> None:
        self.http = http
        self.base_url = base_url

    async def lists(self, token: str) -> list[TaskList]:
        raise NotImplementedError

    async def tasks(self, token: str, task_list: TaskList) -> list[GoogleTask]:
        raise NotImplementedError
