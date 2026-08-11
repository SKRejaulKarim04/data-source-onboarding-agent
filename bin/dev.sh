#!/usr/bin/env bash
# Hot-reloading development.
#
#   uvicorn  :8001  — API, reloads on Python changes
#   vite     :5173  — UI, hot-reloads on React changes, proxies /api to uvicorn
#
# Open the Vite URL. Killing this script stops both processes.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_venv
load_env

API_PORT="${API_PORT:-8001}"
UI_DIR="$ROOT_DIR/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js 18+, or use 'npm run serve' instead." >&2
  exit 1
fi
[[ -d "$UI_DIR/node_modules" ]] || npm --prefix "$UI_DIR" install

"$UVICORN_VENV" dsoa.api.main:app --reload --port "$API_PORT" &
API_PID=$!

# Without this the API keeps the port when Vite exits or you hit Ctrl-C.
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

DSOA_API_URL="http://127.0.0.1:$API_PORT" npm --prefix "$UI_DIR" run dev
