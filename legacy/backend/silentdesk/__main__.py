"""Entry point: `python -m silentdesk`, started by the desktop app with
stdin and stdout connected to it. The composition root: wires the Rust
adapters into the ports and serves until the app closes stdin."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from .adapters import rust
from .adapters.http import make_client
from .app import App
from .core import errors
from .core.ports import Config, Host


async def main() -> None:
    peer = await rust.connect_stdio()
    http = make_client()
    app: App | None = None
    background: set[asyncio.Task] = set()

    async def handle(method: str, params: dict[str, Any]) -> Any:
        nonlocal app
        if method == "init":
            # The first request: secrets and settings, held in memory only.
            if app is not None:
                raise errors.AppError("Already started.")
            config = params.get("config") or {}
            host = Host(
                store=rust.RustStore(peer),
                secrets=rust.RustSecrets(peer, params.get("secrets") or {}),
                browser=rust.RustBrowser(peer),
                events=rust.RustEvents(peer),
                config=Config(
                    google_client_id=config.get("googleClientId"),
                    google_client_secret=config.get("googleClientSecret"),
                    slack_client_id=config.get("slackClientId"),
                    slack_redirect_port=config.get("slackRedirectPort"),
                ),
            )
            app = App(host, http)
            task = asyncio.create_task(app.auto_sync.run())
            background.add(task)
            return None
        if app is None:
            raise errors.AppError("The backend is still starting. Try again.")
        return await app.call(method, params)

    try:
        await peer.serve(handle)
    finally:
        for task in background:
            task.cancel()
        await http.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
