#!/usr/bin/env bash
# Prepares the Python backend for a release bundle, in
# src-tauri/resources/backend/:
#   python/      a standalone Python (python-build-standalone, through uv)
#                with the backend's runtime dependencies installed
#   silentdesk/  the backend's code
# `pnpm release` runs this, then `tauri build`, which ships the folder as the
# app's `backend` resource. macOS and Linux; run on the platform you build for.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_VERSION="${SILENTDESK_PYTHON_VERSION:-3.13}"
OUT=src-tauri/resources/backend
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

rm -rf "$OUT"
mkdir -p "$OUT"

uv python install "$PYTHON_VERSION" --install-dir "$TMP/pythons" --no-bin
python_bin="$(find "$TMP/pythons" -path '*/bin/python3' | head -n 1)"
cp -R "$(dirname "$(dirname "$python_bin")")" "$OUT/python"
# Not needed at runtime: headers, docs, Tk, pip, the test suite.
py="$OUT/python"
rm -rf "$py/include" "$py/share" "$py"/lib/pkgconfig "$py"/lib/itcl* "$py"/lib/tcl* "$py"/lib/tk* \
  "$py"/lib/libtcl* "$py"/lib/libtk* "$py"/bin/idle* "$py"/bin/pip* "$py"/bin/pydoc* \
  "$py"/lib/python3.*/{test,idlelib,tkinter,turtledemo,ensurepip,pydoc_data,lib2to3} \
  "$py"/lib/python3.*/config-* "$py"/lib/python3.*/lib-dynload/_tkinter* \
  "$py"/lib/python3.*/site-packages/pip*

(cd backend && uv export --frozen --no-dev --no-hashes --no-emit-project --output-file "$TMP/requirements.txt" > /dev/null)
uv pip install --python "$OUT/python/bin/python3" --break-system-packages --no-cache \
  -r "$TMP/requirements.txt"

cp -R backend/silentdesk "$OUT/silentdesk"
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "Backend bundled in $OUT ($(du -sh "$OUT" | cut -f1))."
