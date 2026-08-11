#!/usr/bin/env bash
# Usage: bin/lint.sh [fix]  (no arg = check only)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_venv

TARGETS=(src tests eval scripts)

if [[ "${1:-}" == "fix" ]]; then
  "$RUFF_VENV" check --fix "${TARGETS[@]}"
  "$BLACK_VENV" "${TARGETS[@]}"
else
  "$RUFF_VENV" check "${TARGETS[@]}"
  "$BLACK_VENV" --check "${TARGETS[@]}"
fi
