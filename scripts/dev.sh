#!/usr/bin/env bash
# Mini-README: Local development launcher with configurable port and live reload.
set -euo pipefail
PORT="${1:-${PORT:-8000}}"
export PORT
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
