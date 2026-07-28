#!/usr/bin/env bash
# Paperless AOT — start the portal on http://127.0.0.1:8000
# Linux/macOS. On macOS you can also double-click start-mac.command instead.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

# Prefer the project virtual environment when install-mac.command created one.
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi

cd "$ROOT/backend"

if ! "$PY" -c "import fastapi, uvicorn, openpyxl" 2>/dev/null; then
  echo "==> installing dependencies"
  if ! "$PY" -m pip install -r requirements.txt; then
    echo
    echo "pip refused to install into this Python (common on macOS/Homebrew)."
    echo "Create a virtual environment instead, then re-run this script:"
    echo "    python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"
    exit 1
  fi
fi

if [ ! -f "$ROOT/data/paperless_aot.db" ]; then
  echo "==> empty database, loading sample messages"
  "$PY" "$ROOT/scripts/seed.py"
fi

echo "==> Paperless AOT running at http://${HOST}:${PORT}"
exec "$PY" -m uvicorn main:app --host "$HOST" --port "$PORT" "$@"
