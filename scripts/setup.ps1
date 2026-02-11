<#
.SYNOPSIS
    One-command Windows setup for FM TimeTracker.

.DESCRIPTION
    Creates/uses a local .venv, installs dependencies, creates .env from
    .env.example, fills secure defaults for sensitive values, and runs Alembic
    migrations so first-time setup is predictable and repeatable.
#>

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "[setup] Repository root: $repoRoot"

$venvPath = Join-Path $repoRoot ".venv"
$activatePath = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $venvPath)) {
    Write-Host "[setup] Creating virtual environment (.venv)"
    python -m venv .venv
} else {
    Write-Host "[setup] Virtual environment already exists (.venv)"
}

if (-not (Test-Path $activatePath)) {
    throw "[setup] Activation script not found at $activatePath"
}

. $activatePath

Write-Host "[setup] Upgrading pip"
python -m pip install --upgrade pip

Write-Host "[setup] Installing dependencies"
python -m pip install --upgrade -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "[setup] Creating .env from .env.example"
    Copy-Item .env.example .env
} else {
    Write-Host "[setup] .env already exists (will keep your values)"
}

Write-Host "[setup] Ensuring secure .env defaults"
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
    '# Generated and maintained by scripts/setup.ps1 (safe to edit afterwards).'
]
for key in managed:
    output.append(f'{key}={values[key]}')

for key in order:
    if key not in managed:
        output.append(f'{key}={values[key]}')

env_path.write_text('\n'.join(output) + '\n', encoding='utf-8')
print('[setup] .env updated with required keys and secure defaults.')
PY

Write-Host "[setup] Running database migrations"
alembic upgrade head

Write-Host ""
Write-Host "[setup] Done. Next steps:"
Write-Host "  1) .\.venv\Scripts\Activate.ps1"
Write-Host "  2) .\scripts\dev.ps1"
Write-Host "  3) Open http://localhost:8000"
