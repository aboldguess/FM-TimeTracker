# FM TimeTracker

Enterprise browser app for programme/project delivery: planning, timesheets, leave, and admin controls.

## Quick Start (recommended)

### Linux / macOS / Raspberry Pi
```bash
git clone <your-repo-url>
cd FM-TimeTracker
./scripts/setup.sh
./scripts/dev.sh
```

### Windows (PowerShell)
```powershell
git clone <your-repo-url>
cd FM-TimeTracker
.\scripts\setup.ps1
.\scripts\dev.ps1
```

Open: `http://localhost:8000`

> `scripts/setup.*` handles virtual environment creation, dependency installation,
> `.env` creation, secure default generation, and `alembic upgrade head`.

---

## Manual Setup (if you prefer explicit steps)

1. Create and activate a virtual environment.
2. Install dependencies from `requirements.txt`.
3. Copy `.env.example` to `.env` and set secure values (`SECRET_KEY`, bootstrap admin credentials).
4. Run migrations: `alembic upgrade head`.
5. Start app: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.

---

## Required Environment Variables

Defined in `.env.example`:

- `SECRET_KEY`: strong random value (required)
- `DATABASE_URL`: SQLite local default provided
- `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`: first-login admin
- `SECURE_BOOTSTRAP_ONBOARDING`: `true` recommended
- `SECURE_COOKIES`: set `true` in production

Optional:

- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`

> Bootstrap credentials are one-time seed values. After first startup creates
> an admin account, changing `BOOTSTRAP_ADMIN_PASSWORD` in `.env` does **not**
> rotate that existing account password.

---

## Daily Development Commands

```bash
# Linux/macOS
./scripts/dev.sh

# Windows PowerShell
.\scripts\dev.ps1

# Test suite
pytest

# If first startup already happened and you need to rotate the bootstrap admin password
python scripts/reset_bootstrap_admin_password.py --password "<new-strong-password>"

# Nuclear option: fully reset local app state and rebuild from scratch (destructive)
./scripts/nuclear_reset.sh --yes-i-understand

# Windows PowerShell equivalent
.\scripts\nuclear_reset.ps1 -ConfirmReset
```

Health check: `GET /health`

---


## Nuclear Reset (Destructive Recovery)

Use this only when your local environment is badly broken and normal setup/troubleshooting has failed.

What it deletes locally:
- `.venv`
- `.env`
- local SQLite files (`*.db`, `*.sqlite`, `*.sqlite3`)
- Python caches (`__pycache__`, `*.pyc`)

After deletion, it automatically re-runs setup to rebuild a clean baseline.

### Linux / macOS / Raspberry Pi
```bash
./scripts/nuclear_reset.sh --yes-i-understand
```

### Windows (PowerShell)
```powershell
.\scripts\nuclear_reset.ps1 -ConfirmReset
```

## Deployment (Render)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Set env vars:** `SECRET_KEY`, `DATABASE_URL` (managed Postgres recommended), `SECURE_COOKIES=true`, bootstrap admin vars, optional Stripe keys.

---

## Architecture Summary

- `app/main.py`: FastAPI app entrypoint and routes
- `app/models.py`: SQLAlchemy models
- `app/dependencies.py`: auth + RBAC guards
- `app/security.py`: password hashing and signed sessions
- `app/templates/*` + `app/static/styles.css`: UI templates/styles
- `scripts/setup.sh` / `scripts/setup.ps1`: first-time setup automation
- `scripts/dev.sh` / `scripts/dev.ps1`: local launchers
- `scripts/nuclear_reset.sh` / `scripts/nuclear_reset.ps1`: destructive local rebuild helpers

---

## Security Notes

- Passwords are Argon2-hashed.
- Session cookies are signed and HTTP-only.
- RBAC checks are enforced server-side.
- Rotate bootstrap admin credentials after first setup.
- If bootstrap credentials are lost after first setup, use
  `scripts/reset_bootstrap_admin_password.py` to securely reset and force a
  change on next login.

---

## First boot login troubleshooting

If first login fails, work through these checks in order.

### 1) Verify `.env` location and the effective runtime values loaded

The app loads env values from the repo-root `.env` file (absolute path)
defined in `app/config.py`.

#### Linux / macOS / Raspberry Pi (bash/zsh)
```bash
pwd
test -f .env && echo ".env found at: $(pwd)/.env" || echo "Missing .env in repo root"
python -c "from app.config import ENV_FILE_PATH, settings; print('ENV_FILE_PATH=', ENV_FILE_PATH); print('effective bootstrap email=', settings.bootstrap_admin_email); print('effective secure_bootstrap_onboarding=', settings.secure_bootstrap_onboarding)"
```

#### Windows PowerShell
```powershell
Get-Location
if (Test-Path .env) { Write-Host ".env found at: $((Resolve-Path .env).Path)" } else { Write-Host "Missing .env in repo root" }
python -c "from app.config import ENV_FILE_PATH, settings; print('ENV_FILE_PATH=', ENV_FILE_PATH); print('effective bootstrap email=', settings.bootstrap_admin_email); print('effective secure_bootstrap_onboarding=', settings.secure_bootstrap_onboarding)"
```

#### Windows Command Prompt (cmd.exe)
```bat
cd
if exist .env (echo .env found at: %cd%\.env) else (echo Missing .env in repo root)
python -c "from app.config import ENV_FILE_PATH, settings; print('ENV_FILE_PATH=', ENV_FILE_PATH); print('effective bootstrap email=', settings.bootstrap_admin_email); print('effective secure_bootstrap_onboarding=', settings.secure_bootstrap_onboarding)"
```

### 2) Remember bootstrap credentials are one-time seed values

- `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` are only consumed when
  startup finds **no admin user** in the database.
- Once an admin exists, changing those env values does **not** overwrite that
  existing admin password.

### 3) Check whether your DB already contains an admin

If this returns `admin_count > 0`, the bootstrap seed has already been consumed.

#### Linux / macOS / Raspberry Pi (bash/zsh)
```bash
python -c "from sqlalchemy import select, func; from app.database import SessionLocal; from app.models import User, Role; db=SessionLocal(); print({'admin_count': db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN)) or 0}); db.close()"
```

#### Windows PowerShell
```powershell
python -c "from sqlalchemy import select, func; from app.database import SessionLocal; from app.models import User, Role; db=SessionLocal(); print({'admin_count': db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN)) or 0}); db.close()"
```

#### Windows Command Prompt (cmd.exe)
```bat
python -c "from sqlalchemy import select, func; from app.database import SessionLocal; from app.models import User, Role; db=SessionLocal(); print({'admin_count': db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN)) or 0}); db.close()"
```

### 4) Reset bootstrap admin password when seed values are already consumed

Use this when an admin already exists and you cannot sign in with expected credentials.

#### Linux / macOS / Raspberry Pi (bash/zsh)
```bash
python scripts/reset_bootstrap_admin_password.py --password "<new-strong-password>"
```

#### Windows PowerShell
```powershell
python .\scripts\reset_bootstrap_admin_password.py --password "<new-strong-password>"
```

#### Windows Command Prompt (cmd.exe)
```bat
python scripts\reset_bootstrap_admin_password.py --password "<new-strong-password>"
```

### 5) Check the new auth/bootstrap diagnostics in logs

Look for these lines in app logs while reproducing the login issue:

- `Bootstrap startup status: any_admin_exists=... bootstrap_admin_email_exists=... bootstrap_seed_values=used|ignored`
- `login_validation_failed source=... content_type=... email_key_present=... password_key_present=...`
- `login_validation_error_item loc=... type=... msg=...`

Example log filtering:

#### Linux / macOS / Raspberry Pi (bash/zsh)
```bash
# if logs are in a file
rg -n "Bootstrap startup status|login_validation_failed|login_validation_error_item" <path-to-log-file>

# or from live uvicorn output
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee /tmp/fm.log
rg -n "Bootstrap startup status|login_validation_failed|login_validation_error_item" /tmp/fm.log
```

#### Windows PowerShell
```powershell
# if logs are in a file
Select-String -Path .\fm.log -Pattern "Bootstrap startup status|login_validation_failed|login_validation_error_item"

# or from live uvicorn output
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload *>&1 | Tee-Object -FilePath .\fm.log
Select-String -Path .\fm.log -Pattern "Bootstrap startup status|login_validation_failed|login_validation_error_item"
```

#### Windows Command Prompt (cmd.exe)
```bat
REM if logs are in a file
findstr /n /c:"Bootstrap startup status" /c:"login_validation_failed" /c:"login_validation_error_item" fm.log
```

---

## Major Feature Log

1. **Nuclear reset recovery scripts for full local rebuilds** (branch: current working branch)
2. **Setup automation refresh + onboarding simplification** (branch: current working branch)
3. **Alembic migration workflow + timesheet timestamp migration** (branch: current working branch)
4. **Role-aware operations hubs + sidebar navigation** (branch: current working branch)
5. **Bootstrap platform implementation** (branch: current working branch)
6. **Timesheet governance + customer management foundations** (branch: current working branch)
7. **Temporary password resets with enforced first-login change** (branch: current working branch)

## Feature Status Roadmap

### User-Facing
- [x] Friendly landing splash page
- [x] Secure login and role-based dashboards
- [x] User role hierarchy (admin/programme manager/project manager/staff)
- [x] Project → work package → task structure
- [x] Resource requirement planning and monitoring records
- [x] Timesheet entry system for all users
- [x] Annual leave request and admin approval/denial flow
- [x] Sick leave recording
- [x] Cost/bill rate configuration per user for P&L inputs
- [x] Admin/profile menu UX placeholders with learning zone/my details/subscription options
- [x] Role-aware sidebar and operational pages for timesheets, leave, projects, programmes, company, and site management
- [x] Customer directory with CRUD and project-customer linking
- [x] Timesheet weekly submissions, approvals, and audit trail visibility
- [x] Temporary password reset and forced password update on next login
- [ ] Rich drag-drop planning UI and Gantt visualizations
- [ ] Email/Slack notifications for approvals and project alerts

### Under the Hood
- [x] FastAPI + SQLAlchemy architecture
- [x] Signed cookie session auth and password hashing
- [x] Startup bootstrap admin provisioning
- [x] Local scripts and production-ready ASGI deployment path
- [x] Pytest smoke tests
- [ ] Full CI/CD pipeline (lint, test, security scans)
- [x] Postgres/SQLite migration workflow via Alembic
- [x] Fine-grained audit log trail
- [x] Nuclear local reset scripts for destructive recovery
