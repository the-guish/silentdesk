#!/usr/bin/env bash
# Starts SilentDesk in development mode, with settings from .env.
# Usage: ./dev.sh [extra arguments for `tauri dev`]
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
else
  echo "No .env file: Gmail will be unavailable." >&2
  echo "To set it up: cp .env.example .env, then see docs/setup/gmail.md." >&2
fi

if [ ! -d node_modules ]; then
  pnpm install
fi

exec pnpm tauri dev "$@"
