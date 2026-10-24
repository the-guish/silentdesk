from __future__ import annotations

from ....infra.http import Http
from ..core.gmail import GmailMessage
from ..ports.gmail_api import Changes, GmailApi, InboxPage


class GmailHttpApi(GmailApi):
    def __init__(self, http: Http, base_url: str) -> None:
        self.http = http
        self.base_url = base_url

    async def account_email(self, token: str) -> str:
        raise NotImplementedError

    async def inbox(self, token: str, page_token: str | None) -> InboxPage:
        raise NotImplementedError

    async def message(self, token: str, message_id: str) -> GmailMessage:
        raise NotImplementedError

    async def changes(self, token: str, history_id: str) -> Changes:
        raise NotImplementedError

    async def send(self, token: str, raw: bytes, thread_id: str) -> None:
        raise NotImplementedError

    async def trash(self, token: str, message_id: str) -> None:
        raise NotImplementedError
