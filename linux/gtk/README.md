# SilentDesk for Linux

The Linux app, in Python with GTK4 and libadwaita. It reaches the core in [`../core`](../core) through `silentdesk.api`, and uses `silentdesk.contract` for the core's types.

## How it works

- **The queue:** every topic, newest first, with its service, who wrote last and when. The search box filters it by title, service and people.
- **Syncing:** at startup, every 2 minutes, and when the window comes back into focus if the last round started more than 30 seconds ago. **Refresh** starts a round at once. The footer says when topics last changed. Failures show as a toast, and the old topics stay.
- **Threads:** GTK runs on the main thread. The core's calls run on one background thread with one asyncio loop (`worker.py`), and their results come back to the main thread through `GLib.idle_add`. One loop for every call keeps the core's per-service locks meaningful.

| File | What it is |
|------|------------|
| `src/silentdesk_gtk/app.py` | The application: one desk, one worker, one window |
| `src/silentdesk_gtk/window.py` | The main window: queue, search, Refresh and automatic syncing |
| `src/silentdesk_gtk/topic_list.py` | The list view and its rows |
| `src/silentdesk_gtk/format.py` | How topics read: names, dates, search; tested without a display |
| `src/silentdesk_gtk/worker.py` | The background thread for the core |

## System packages

GTK, libadwaita and PyGObject come from the system, not from PyPI. On Debian or Ubuntu:

```sh
sudo apt-get install gir1.2-adw-1 gir1.2-gtk-4.0 python3-gi
```

It needs libadwaita 1.4 or newer (Ubuntu 24.04, Debian 13).

## Run

```sh
./run.sh
```

`run.sh` creates `.venv` on the system Python (`/usr/bin/python3`) with access to its packages, installs the core into it, and starts the app. If `python3-gi` is installed for another Python, set `SILENTDESK_GTK_PYTHON` to it, then delete `.venv` and run again.

## Test

```sh
uv run pytest -q                 # with a display
xvfb-run -a uv run pytest -q     # without one
```
