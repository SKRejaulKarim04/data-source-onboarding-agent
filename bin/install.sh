#!/usr/bin/env bash
# Create venv and install dependencies. Cross-platform (macOS/Linux/Windows Git Bash).
#
# Deliberately does not source lib.sh: its venv-layout detection (bin/ vs
# Scripts/) inspects .venv, which does not exist yet on a first run here.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

"$PY" -m venv .venv

if [[ -d ".venv/Scripts" ]]; then
  VENV_BIN=".venv/Scripts"
  EXE=".exe"
else
  VENV_BIN=".venv/bin"
  EXE=""
fi

"$VENV_BIN/pip$EXE" install --upgrade pip
"$VENV_BIN/pip$EXE" install -r requirements.txt
"$VENV_BIN/pip$EXE" install -e .

# The React front end. Optional: without Node.js the server falls back to the
# single-file UI, so a missing npm is a warning, not a failed install.
if command -v npm >/dev/null 2>&1; then
  npm --prefix frontend install
  npm --prefix frontend run build
else
  echo ""
  echo "npm not found — skipping the React build. Install Node.js 18+ and run:"
  echo "  npm run ui:build"
fi

echo ""
echo "Next:  source $VENV_BIN/activate  &&  npm test"
echo "Then:  npm run serve      # http://localhost:8001"
