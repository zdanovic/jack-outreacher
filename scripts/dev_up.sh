#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[dev] Starting API (uvicorn) ..."
(
  cd "$ROOT_DIR"
  source venv/bin/activate
  uvicorn src.app.api:app --host 0.0.0.0 --port 8000 >/tmp/tg-api.log 2>&1 &
  echo $! > /tmp/tg-api.pid
)

echo "[dev] Starting UI (Vite) ..."
(
  cd "$ROOT_DIR/ui"
  if [ ! -d node_modules ]; then
    npm install >/tmp/tg-ui-install.log 2>&1
  fi
  npm run dev -- --host 0.0.0.0 --port 5173 >/tmp/tg-ui.log 2>&1 &
  echo $! > /tmp/tg-ui.pid
)

echo "[dev] Stack started:"
echo "  API: http://127.0.0.1:8000"
echo "  UI:  http://127.0.0.1:5173"
echo
echo "Logs: /tmp/tg-api.log, /tmp/tg-ui.log. PIDs: /tmp/tg-api.pid, /tmp/tg-ui.pid"
