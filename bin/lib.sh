# Shared helpers, sourced by every script in bin/.
# Works under bash on macOS/Linux and under Git Bash on Windows.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Windows venvs use Scripts/*.exe, POSIX venvs use bin/*.
if [[ -d ".venv/Scripts" ]]; then
  VENV_BIN=".venv/Scripts"
  EXE=".exe"
else
  VENV_BIN=".venv/bin"
  EXE=""
fi

PYTHON_VENV="$VENV_BIN/python$EXE"
PIP_VENV="$VENV_BIN/pip$EXE"
PYTEST_VENV="$VENV_BIN/pytest$EXE"
RUFF_VENV="$VENV_BIN/ruff$EXE"
BLACK_VENV="$VENV_BIN/black$EXE"
UVICORN_VENV="$VENV_BIN/uvicorn$EXE"

# `python3` doesn't exist on a stock Windows install; `python` does there
# (via the py launcher shim) and is usually also fine on macOS/Linux.
system_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
  else
    echo "python"
  fi
}

require_venv() {
  if [[ ! -x "$PYTHON_VENV" ]]; then
    echo "No .venv found. Run: npm run setup" >&2
    exit 1
  fi
}

# Loads .env into the current process's environment, if present, without
# requiring the caller to `set -a; source .env; set +a` themselves.
load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT_DIR/.env"
    set +a
  fi
}
