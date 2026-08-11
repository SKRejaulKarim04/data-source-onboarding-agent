#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

rm -rf .pytest_cache .ruff_cache .coverage htmlcov frontend/dist
find . -type d -name "__pycache__" -not -path "./.venv/*" -not -path "./node_modules/*" -exec rm -rf {} +
