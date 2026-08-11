#!/usr/bin/env bash
# Run the web app on http://localhost:8001 — API and React UI from one origin.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_venv
load_env

# Builds the front end on first run; a no-op once frontend/dist exists.
bash "$ROOT_DIR/bin/ui.sh" ensure

PORT="${PORT:-8001}"
echo "→ http://localhost:$PORT"
exec "$UVICORN_VENV" dsoa.api.main:app --reload --port "$PORT"
