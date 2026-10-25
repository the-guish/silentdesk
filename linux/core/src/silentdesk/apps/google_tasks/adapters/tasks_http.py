"""The Google Tasks REST API, read-only, and Google's user info for the email."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from ....contract import AuthError, Http, NetworkError, RemoteError
from ..domain.tasks import GoogleTask, TaskList
from ..ports.tasks_api import TasksApi

SERVICE = "tasks"
# Stop paging after this many pages of 100, per list.
MAX_PAGES = 20
# Where a task came from, by assignmentInfo.surfaceType, then by link type.
SURFACES = {"DOCUMENT": "Docs", "SPACE": "Chat", "GMAIL": "Gmail"}
LINKS = {"email": "Gmail", "chat_message": "Chat"}


class TasksHttpApi(TasksApi):
    def __init__(self, http: Http, api_base: str, userinfo_url: str) -> None:
        self.http = http
        # Such as https://tasks.googleapis.com/tasks/v1.
        self.api_base = api_base
        self.userinfo_url = userinfo_url

    async def _get(self, url: str, token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = await self.http.request("GET", url, params=params, headers={"Authorization": f"Bearer {token}"})
        try:
            body = json.loads(response.body) if response.body else None
        except ValueError:
            body = None
        if response.status == 401:
            raise AuthError(SERVICE, "Google rejected the access token.")
        if not 200 <= response.status < 300:
            error = body.get("error") if isinstance(body, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise RemoteError(
                SERVICE, f"Google Tasks answered {response.status}: {message or 'no details'}.", response.status
            )
        if not isinstance(body, dict):
            raise NetworkError(SERVICE, "Google's answer could not be read.")
        return body

    async def _all(self, url: str, token: str, params: dict[str, str]) -> list[Any]:
        items: list[Any] = []
        page_token = None
        for _ in range(MAX_PAGES):
            page = await self._get(url, token, {**params, **({"pageToken": page_token} if page_token else {})})
            found = page.get("items", [])
            if not isinstance(found, list):
                raise NetworkError(SERVICE, "Google's answer could not be read.")
            items += found
            page_token = page.get("nextPageToken")
            if not isinstance(page_token, str):
                break
        return items

    async def email(self, token: str) -> str:
        email = (await self._get(self.userinfo_url, token)).get("email")
        if not isinstance(email, str):
            raise NetworkError(SERVICE, "Google did not say which account signed in.")
        return email

    async def lists(self, token: str) -> list[TaskList]:
        found = await self._all(f"{self.api_base}/users/@me/lists", token, {"maxResults": "100"})
        return [
            TaskList(item["id"], item.get("title") or "")
            for item in found
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    async def tasks(self, token: str, task_list: TaskList) -> list[GoogleTask]:
        found = await self._all(
            f"{self.api_base}/lists/{quote(task_list.list_id, safe='')}/tasks",
            token,
            {
                "maxResults": "100",
                "showCompleted": "false",
                "showHidden": "false",
                "showDeleted": "false",
                "showAssigned": "true",
            },
        )
        return [_task(item, task_list) for item in found if isinstance(item, dict) and isinstance(item.get("id"), str)]


def _task(item: dict[str, Any], task_list: TaskList) -> GoogleTask:
    assignment = item.get("assignmentInfo")
    surface = assignment.get("surfaceType") if isinstance(assignment, dict) else None
    links = [link.get("type") for link in item.get("links", []) if isinstance(link, dict)]
    origin = SURFACES.get(surface) or next((LINKS[kind] for kind in links if kind in LINKS), None)
    due = item.get("due")
    return GoogleTask(
        task_id=item["id"],
        list_id=task_list.list_id,
        list_title=task_list.title,
        title=item.get("title") or "",
        completed=item.get("status") == "completed",
        deleted=item.get("deleted") is True,
        due=due[:10] if isinstance(due, str) and len(due) >= 10 else None,
        origin=origin,
        url=item.get("webViewLink") or "https://tasks.google.com/",
        updated=item.get("updated") or "",
    )
