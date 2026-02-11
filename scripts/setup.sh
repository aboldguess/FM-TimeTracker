#!/usr/bin/env bash
# Mini-README: One-command local setup for Linux/macOS/Raspberry Pi.
# Creates a virtualenv, installs dependencies, creates .env from .env.example,
# generates secure defaults for sensitive values, and runs database migrations.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[setup] Repository root: $REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[setup] ERROR: python3 is required but was not found." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[setup] Creating virtual environment (.venv)"
  python3 -m venv .venv
else
  echo "[setup] Virtual environment already exists (.venv)"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] Upgrading pip"
python -m pip install --upgrade pip

echo "[setup] Installing dependencies"
python -m pip install --upgrade -r requirements.txt

if [ ! -f ".env" ]; then
  echo "[setup] Creating .env from .env.example"
  cp .env.example .env
else
  echo "[setup] .env already exists (will keep your values)"
fi

echo "[setup] Ensuring secure .env defaults"
python - <<'PY'
from pathlib import Path
import secrets

env_path = Path('.env')
lines = env_path.read_text(encoding='utf-8').splitlines()
values = {}
order = []
for line in lines:
    if not line or line.strip().startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    key = key.strip()
    values[key] = value
    order.append(key)

def upsert(key: str, value: str) -> None:
    if key not in values or not values[key].strip() or values[key].startswith('replace-with-'):
        values[key] = value
        if key not in order:
            order.append(key)

upsert('SECRET_KEY', secrets.token_urlsafe(48))
upsert('BOOTSTRAP_ADMIN_PASSWORD', secrets.token_urlsafe(24))
upsert('BOOTSTRAP_ADMIN_EMAIL', 'admin@change.me')
upsert('SECURE_BOOTSTRAP_ONBOARDING', 'true')

# Preserve comments/order where possible; rebuild with managed keys first then extras.
managed = [
    'SECRET_KEY', 'DATABASE_URL', 'ENVIRONMENT', 'DEBUG', 'HOST', 'PORT',
    'SECURE_COOKIES', 'BOOTSTRAP_ADMIN_EMAIL', 'BOOTSTRAP_ADMIN_PASSWORD',
    'SECURE_BOOTSTRAP_ONBOARDING', 'STRIPE_SECRET_KEY', 'STRIPE_PUBLISHABLE_KEY'
]

for key in managed:
    if key not in values:
        values[key] = ''

output = [
    '# Mini-README: Runtime environment for FM TimeTracker.',
    '# Generated and maintained by scripts/setup.sh (safe to edit afterwards).'
]
for key in managed:
    output.append(f'{key}={values[key]}')

for key in order:
    if key not in managed:
        output.append(f'{key}={values[key]}')

env_path.write_text('\n'.join(output) + '\n', encoding='utf-8')
print('[setup] .env updated with required keys and secure defaults.')
PY

echo "[setup] Running database migrations"
alembic upgrade head

echo ""
echo "[setup] Done. Next steps:"
echo "  1) source .venv/bin/activate"
echo "  2) ./scripts/dev.sh"
echo "  3) Open http://localhost:8000"
