#!/usr/bin/env bash
# Paperless AOT — start the portal on http://127.0.0.1:8000
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

cd "$ROOT/backend"

if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "==> installing dependencies"
  python3 -m pip install -r requirements.txt
fi

if [ ! -f "$ROOT/data/paperless_aot.db" ]; then
  echo "==> empty database, loading sample messages"
  python3 "$ROOT/scripts/seed.py"
fi

echo "==> Paperless AOT running at http://${HOST}:${PORT}"
exec python3 -m uvicorn main:app --host "$HOST" --port "$PORT" "$@"
