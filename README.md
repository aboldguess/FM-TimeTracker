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

---

## Daily Development Commands

```bash
# Linux/macOS
./scripts/dev.sh

# Windows PowerShell
.\scripts\dev.ps1

# Test suite
pytest
```

Health check: `GET /health`

---

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

---

## Security Notes

- Passwords are Argon2-hashed.
- Session cookies are signed and HTTP-only.
- RBAC checks are enforced server-side.
- Rotate bootstrap admin credentials after first setup.

---

## Major Feature Log

1. **Setup automation refresh + onboarding simplification** (branch: current working branch)
2. **Alembic migration workflow + timesheet timestamp migration** (branch: current working branch)
3. **Role-aware operations hubs + sidebar navigation** (branch: current working branch)
4. **Bootstrap platform implementation** (branch: current working branch)
5. **Timesheet governance + customer management foundations** (branch: current working branch)
6. **Temporary password resets with enforced first-login change** (branch: current working branch)

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
