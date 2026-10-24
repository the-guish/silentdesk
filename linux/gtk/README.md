# SilentDesk for Linux

The Linux app, in Python with GTK4 and libadwaita. It reaches the core in [`../core`](../core) through `silentdesk.api` only.

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
