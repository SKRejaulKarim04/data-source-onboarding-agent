#!/usr/bin/env bash
# Generic runner: loads .env, then hands off to the venv's python.
# Usage: bin/run-py.sh <script> [args...]
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_venv
load_env
exec "$PYTHON_VENV" "$@"
