#!/usr/bin/env bash
# Mini-README: Nuclear local reset for FM TimeTracker (Linux/macOS/Raspberry Pi).
# This script DESTROYS local runtime state (.venv, .env, sqlite DB, caches) and
# rebuilds from scratch via scripts/setup.sh. Use when local state is corrupted.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CONFIRMATION="${1:-}"
if [[ "$CONFIRMATION" != "--yes-i-understand" ]]; then
  cat <<'MSG'
[nuclear-reset] Refusing to run without explicit confirmation.

This command permanently deletes LOCAL DEVELOPMENT state:
  - .venv
  - .env
  - SQLite database files (*.db / *.sqlite / *.sqlite3)
  - Python cache folders

If you are sure, run:
  ./scripts/nuclear_reset.sh --yes-i-understand
MSG
  exit 1
fi

echo "[nuclear-reset] Repository root: $REPO_ROOT"
echo "[nuclear-reset] Starting destructive local reset..."

# Delete virtual environment and local runtime config.
rm -rf .venv
rm -f .env

# Delete local SQLite databases that are commonly used for development.
find . -maxdepth 3 -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print -delete || true

# Delete Python cache artifacts for a clean import/runtime state.
find . -type d -name '__pycache__' -prune -print -exec rm -rf {} + || true
find . -type f -name '*.pyc' -delete || true

# Re-run standard setup to restore a secure, working baseline.
./scripts/setup.sh

echo "[nuclear-reset] Complete. Start the app with ./scripts/dev.sh"
