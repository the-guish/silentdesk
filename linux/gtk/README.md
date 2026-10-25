# SilentDesk for Linux

The Linux app, in Python with GTK4 and libadwaita. It reaches the core in [`../core`](../core) through `silentdesk.api`, and uses `silentdesk.contract` for the core's types.

## How it works

- **The window** opens maximized. Unmaximized, it is 960 by 640.
- **The queue:** every topic, newest first, with an avatar of who wrote last, its service, and when. A topic whose newest item the user wrote reads "Waiting on others". Search opens with the search button, Ctrl+F, or by typing in the queue, and filters by title, service and people.
- **The topic screen:** a topic's items, each with who wrote it, whether it was received or sent, and when, and a button to open it in its service; a note says why there is no text. Where the service keeps a conversation (Slack), its recent messages are read live and shown instead, never stored. Gmail topics have a reply entry; Ctrl+Enter sends. A Delete button shows on topics their connector marks deletable, and on each deletable item of a topic with several, such as one Gmail message, which moves to the trash; each asks first.
- **Menu and shortcuts:** the main menu holds Services, Keyboard Shortcuts and About. Ctrl+F searches, Ctrl+R or F5 refreshes, Ctrl+, opens Services, Ctrl+? lists the shortcuts, Escape goes back, Ctrl+Enter sends a reply, Ctrl+W closes the window and Ctrl+Q quits.
- **Services:** the Services dialog lists every service. GitHub and Jira connect with a form; Gmail, Google Tasks and Slack sign in through the browser. A service that connects syncs at once; one that disconnects drops its topics, after asking.
- **Syncing:** at startup, every 2 minutes, and when the window comes back into focus if the last round started more than 30 seconds ago. **Refresh** starts a round at once. The header's subtitle says when topics last changed. Failures show as a toast, and the old topics stay.
- **Threads:** GTK runs on the main thread. The core's calls run on one background thread with one asyncio loop (`worker.py`), and their results come back to the main thread through `GLib.idle_add`, at default priority so they arrive while an animation runs. One loop for every call keeps the core's per-service locks meaningful.

| File | What it is |
|------|------------|
| `src/silentdesk_gtk/app.py` | The application: one desk, one worker, one window |
| `src/silentdesk_gtk/window.py` | The main window: queue, search, Refresh, automatic syncing, the main menu and shortcuts, and navigation to the rest |
| `src/silentdesk_gtk/topic_list.py` | The list view and its rows |
| `src/silentdesk_gtk/topic_page.py` | The topic screen: items or conversation, reply and delete |
| `src/silentdesk_gtk/services_dialog.py` | The Services dialog: connect forms and Disconnect |
| `src/silentdesk_gtk/services.py` | What each service asks for, and offers; tested without a display |
| `src/silentdesk_gtk/format.py` | How topics read: names, dates, avatars, search; tested without a display |
| `src/silentdesk_gtk/style.py` | The few style rules beyond libadwaita's, for the reply entry |
| `src/silentdesk_gtk/worker.py` | The background thread for the core |

## System packages

GTK, libadwaita and PyGObject come from the system, not from PyPI. On Debian or Ubuntu:

```sh
sudo apt-get install gir1.2-adw-1 gir1.2-gtk-4.0 python3-gi
```

It needs libadwaita 1.5 or newer (Ubuntu 24.04, Debian 13).

## Run

```sh
./run.sh
```

`run.sh` creates `.venv` on the system Python (`/usr/bin/python3`) with access to its packages, installs the core into it, and starts the app. If `python3-gi` is installed for another Python, set `SILENTDESK_GTK_PYTHON` to it, then delete `.venv` and run again.

`run.sh` loads `.env` at the repository root when it exists. It holds the variables in [`spec/cli.md`](../../spec/cli.md), such as `SILENTDESK_GOOGLE_CLIENT_ID`. Gmail, Google Tasks and Slack need them.

## Test

```sh
uv run pytest -q                 # with a display
xvfb-run -a uv run pytest -q     # without one
```
