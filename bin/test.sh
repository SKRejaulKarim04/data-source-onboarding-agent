#!/usr/bin/env bash
# Usage: bin/test.sh [unit|integration]  (no arg = everything)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_venv

MODE="${1:-all}"

case "$MODE" in
  unit)
    exec "$PYTEST_VENV" -m "not integration"
    ;;
  integration)
    load_env
    exec "$PYTEST_VENV" -m integration
    ;;
  all)
    exec "$PYTEST_VENV"
    ;;
  *)
    echo "Unknown test mode: $MODE (expected unit|integration|all)" >&2
    exit 1
    ;;
esac
