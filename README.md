# FM TimeTracker

Enterprise-grade browser platform for programme/project management, resource planning, timesheets, leave workflows, and financial visibility.

## Major Feature Log
1. **Bootstrap platform implementation** (branch: current working branch) – Added secure RBAC backend, dashboards, project hierarchy, resource tracking, leave, sick leave, and subscription/admin controls.

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
- [ ] Rich drag-drop planning UI and Gantt visualizations
- [ ] Email/Slack notifications for approvals and project alerts

### Under the Hood
- [x] FastAPI + SQLAlchemy architecture
- [x] Signed cookie session auth and password hashing
- [x] Startup bootstrap admin provisioning
- [x] Local scripts and production-ready ASGI deployment path
- [x] Pytest smoke tests
- [ ] Full CI/CD pipeline (lint, test, security scans)
- [ ] Postgres-first production migrations (Alembic)
- [ ] Fine-grained audit log trail

---

## Architecture Summary
- `app/main.py` – FastAPI app entry, routes, and startup bootstrap
- `app/models.py` – SQLAlchemy ORM domain models
- `app/dependencies.py` – auth + RBAC guards
- `app/security.py` – password hashing and session token signing
- `app/templates/*` + `app/static/styles.css` – modern browser UI pages
- `scripts/dev.sh` – local launch helper
- `tests/test_health.py` – health endpoint smoke test

## Security Notes
- Passwords are hashed with Argon2 (`passlib` + `argon2-cffi`).
- Session cookies are HTTP-only and signed.
- Role checks are enforced server-side for CRUD boundaries.
- Set a strong `SECRET_KEY` and `SECURE_COOKIES=true` in production.

## Local Setup (Windows / Linux / macOS / Raspberry Pi)

### 1) Clone and enter project
```bash
git clone <your-repo-url>
cd FM-TimeTracker
```

### 2) Create virtual environment

#### Linux/macOS/Raspberry Pi
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Configure environment variables
Create a `.env` file in the repo root (same folder as `README.md`) by copying the example file.
This keeps sensitive values out of source control and makes setup repeatable across OSes.

#### Linux/macOS/Raspberry Pi
```bash
cp .env.example .env
```

#### Windows (PowerShell)
```powershell
Copy-Item .env.example .env
```

Then edit `.env` and add your values. **Always set a strong secret key.** You can generate one:

#### Linux/macOS/Raspberry Pi
```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

#### Windows (PowerShell)
```powershell
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Example values:
```env
SECRET_KEY=replace-with-very-strong-secret
DATABASE_URL=sqlite:///./fm_timetracker.db
ENVIRONMENT=development
DEBUG=true
HOST=0.0.0.0
PORT=8000
SECURE_COOKIES=false
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
```

### 5) Run locally
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Windows (PowerShell) preferred entry point
```powershell
$env:PORT=8000
.\scripts\dev.ps1
```

Open: `http://localhost:8000`

### Bootstrap credentials
- Email: `admin@change.me`
- Password: `ChangeMeNow!123`

Change password immediately by updating the user via API.

## API Usage Examples
### Create a project
```bash
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -H "Cookie: session_token=<token>" \
  -d '{"name":"Project Atlas","description":"Delivery programme","planned_hours":1200}'
```

### Add timesheet entry
```bash
curl -X POST http://localhost:8000/timesheets \
  -H "Content-Type: application/json" \
  -H "Cookie: session_token=<token>" \
  -d '{"entry_date":"2026-01-10","hours":7.5,"description":"Requirements workshop"}'
```

## Deploying on Render.com
1. Create a new Web Service linked to your Git repo.
2. Build command:
   ```bash
   pip install -r requirements.txt
   ```
3. Start command:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Set environment variables:
   - `SECRET_KEY` (strong random string)
   - `DATABASE_URL` (prefer managed Postgres)
   - `SECURE_COOKIES=true`
   - `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` (if enabled)

## Debugging Tips
- Health check: `GET /health`
- Watch startup logs for admin bootstrap messages.
- Run tests: `pytest`
- Enable verbose Uvicorn logs:
  ```bash
  uvicorn app.main:app --reload --log-level debug
  ```
