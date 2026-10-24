#!/usr/bin/env bash
# Runs the GTK app from source. GTK, libadwaita and PyGObject come from the
# system packages, so the environment uses the system Python and its packages.
# Set SILENTDESK_GTK_PYTHON if python3-gi is installed for another Python.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  uv venv --quiet --python "${SILENTDESK_GTK_PYTHON:-/usr/bin/python3}" --system-site-packages
fi
uv sync --quiet

exec uv run --quiet python -m silentdesk_gtk "$@"
