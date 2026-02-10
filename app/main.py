"""Application entrypoint.

This file wires API routes, HTML pages, RBAC enforcement, and startup actions
for the FM TimeTracker browser application.
"""

from datetime import date, datetime, timedelta

import stripe
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import engine, get_db, run_migrations
from app.dependencies import can_manage_target, get_current_user, require_roles
from app.models import (
    AppConfig,
    Customer,
    LeaveRequest,
    LeaveStatus,
    Programme,
    Project,
    ResourceRequirement,
    Role,
    SickLeaveRecord,
    SubscriptionTier,
    Task,
    TimesheetEntry,
    TimesheetEntryAudit,
    TimesheetWeekStatus,
    TimesheetWeekSummary,
    User,
    WorkPackage,
)
from app.schemas import LeaveCreate, LoginRequest, ProjectCreate, SickLeaveCreate, TimesheetCreate, UserCreate, UserUpdate
from app.security import create_session_token, ensure_password_backend, hash_password, verify_password

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def parse_optional_int(raw_value: str | None) -> int | None:
    """Parse optional integer fields from HTML forms without raising FastAPI parsing errors."""
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Enter a valid numeric identifier.") from exc


def parse_optional_float(raw_value: str | None, *, field_label: str) -> float | None:
    """Parse optional floats from HTML forms with clear error messages."""
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Enter a valid number for {field_label}.") from exc


def week_bounds(target_date: date) -> tuple[date, date]:
    """Return Monday-Sunday bounds for the week containing the target date."""
    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def working_hours_for_day(user: User, day: date) -> float:
    """Resolve a user's expected working hours for the provided day."""
    weekday = day.weekday()
    hours_map = {
        0: user.working_hours_mon,
        1: user.working_hours_tue,
        2: user.working_hours_wed,
        3: user.working_hours_thu,
        4: user.working_hours_fri,
        5: user.working_hours_sat,
        6: user.working_hours_sun,
    }
    return hours_map.get(weekday, 0)


def default_working_hours(db: Session) -> dict[str, float]:
    """Load global default working hours from AppConfig with safe fallbacks."""
    defaults = {
        "mon": 8,
        "tue": 8,
        "wed": 8,
        "thu": 8,
        "fri": 8,
        "sat": 0,
        "sun": 0,
    }
    config_values = db.scalars(
        select(AppConfig).where(
            AppConfig.key.in_(
                [
                    "default_hours_mon",
                    "default_hours_tue",
                    "default_hours_wed",
                    "default_hours_thu",
                    "default_hours_fri",
                    "default_hours_sat",
                    "default_hours_sun",
                ]
            )
        )
    ).all()
    mapping = {
        "default_hours_mon": "mon",
        "default_hours_tue": "tue",
        "default_hours_wed": "wed",
        "default_hours_thu": "thu",
        "default_hours_fri": "fri",
        "default_hours_sat": "sat",
        "default_hours_sun": "sun",
    }
    for config in config_values:
        key = mapping.get(config.key)
        if key:
            try:
                defaults[key] = float(config.value)
            except ValueError:
                continue
    return defaults


def approved_hours_for_user(db: Session, user_id: int) -> float:
    """Return total hours from approved timesheet weeks only."""
    approved_weeks = db.scalars(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == user_id,
            TimesheetWeekSummary.status == TimesheetWeekStatus.APPROVED,
        )
    ).all()
    total = 0.0
    for week in approved_weeks:
        total += (
            db.scalar(
                select(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).where(
                    TimesheetEntry.user_id == user_id,
                    TimesheetEntry.entry_date >= week.week_start,
                    TimesheetEntry.entry_date <= week.week_end,
                )
            )
            or 0.0
        )
    return total


def bootstrap_context(db: Session) -> dict[str, object]:
    """Build context for rendering bootstrap admin guidance."""
    admin_count = db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN)) or 0
    bootstrap_exists = (
        db.scalar(
            select(func.count(User.id)).where(
                User.role == Role.ADMIN,
                func.lower(User.email) == settings.bootstrap_admin_email.lower(),
            )
        )
        or 0
    )
    # Only hide bootstrap guidance once a non-bootstrap admin is created.
    non_bootstrap_admins = max(admin_count - bootstrap_exists, 0)
    return {
        "show_bootstrap": admin_count == 0 or non_bootstrap_admins == 0,
        "bootstrap_email": settings.bootstrap_admin_email,
        "bootstrap_password": settings.bootstrap_admin_password,
    }


@app.on_event("startup")
def startup() -> None:
    run_migrations()
    stripe.api_key = settings.stripe_secret_key
    ensure_password_backend()
    with Session(engine) as db:
        admin_exists = db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN))
        if not admin_exists:
            db.add(
                User(
                    email=settings.bootstrap_admin_email,
                    full_name="System Admin",
                    hashed_password=hash_password(settings.bootstrap_admin_password),
                    role=Role.ADMIN,
                    cost_rate=120,
                    bill_rate=250,
                )
            )
            db.commit()


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    with Session(engine) as db:
        bootstrap_details = bootstrap_context(db)
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            **bootstrap_details,
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    with Session(engine) as db:
        bootstrap_details = bootstrap_context(db)
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            **bootstrap_details,
        },
    )


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        payload = LoginRequest(email=email, password=password)
    except ValidationError:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": f"Enter a valid email address (example: {settings.bootstrap_admin_email}).",
                **bootstrap_context(db),
            },
            status_code=400,
        )
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid credentials",
                **bootstrap_context(db),
            },
            status_code=401,
        )
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("session_token", create_session_token(user.id), httponly=True, secure=settings.secure_cookies, samesite="lax")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project_count = db.scalar(select(func.count(Project.id))) or 0
    timesheet_hours = approved_hours_for_user(db, current_user.id)
    pending_leave = db.scalar(select(func.count(LeaveRequest.id)).where(LeaveRequest.status == LeaveStatus.PENDING)) or 0
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "project_count": project_count,
            "timesheet_hours": timesheet_hours,
            "pending_leave": pending_leave,
        },
    )


@app.get("/timesheets", response_class=HTMLResponse)
def timesheets(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    week_start, week_end = week_bounds(today)
    current_week = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == current_user.id,
            TimesheetWeekSummary.week_start == week_start,
        )
    )
    approved_hours = approved_hours_for_user(db, current_user.id)
    entry_count = db.scalar(select(func.count(TimesheetEntry.id)).where(TimesheetEntry.user_id == current_user.id)) or 0
    recent_entries = db.scalars(
        select(TimesheetEntry)
        .where(TimesheetEntry.user_id == current_user.id)
        .order_by(TimesheetEntry.entry_date.desc(), TimesheetEntry.id.desc())
        .limit(6)
    ).all()
    project_options = db.scalars(select(Project).order_by(Project.name.asc())).all()
    task_options = db.scalars(select(Task).order_by(Task.name.asc())).all()
    leave_days = set()
    approved_leave = db.scalars(
        select(LeaveRequest).where(
            LeaveRequest.user_id == current_user.id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.end_date >= week_start,
            LeaveRequest.start_date <= week_end,
        )
    ).all()
    for leave in approved_leave:
        cursor = leave.start_date
        while cursor <= leave.end_date:
            leave_days.add(cursor)
            cursor += timedelta(days=1)
    logged_hours_by_day = {
        row[0]: row[1]
        for row in (
            db.execute(
                select(TimesheetEntry.entry_date, func.coalesce(func.sum(TimesheetEntry.hours), 0.0))
                .where(
                    TimesheetEntry.user_id == current_user.id,
                    TimesheetEntry.entry_date >= week_start,
                    TimesheetEntry.entry_date <= week_end,
                )
                .group_by(TimesheetEntry.entry_date)
            ).all()
        )
    }
    day_statuses = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        logged = float(logged_hours_by_day.get(day, 0.0))
        expected = 0.0 if day in leave_days else working_hours_for_day(current_user, day)
        if expected <= 0 and logged <= 0:
            status = "complete"
        elif logged <= 0:
            status = "missing"
        elif logged < expected:
            status = "partial"
        else:
            status = "complete"
        day_statuses.append(
            {
                "date": day,
                "logged": logged,
                "expected": expected,
                "status": status,
                "is_today": day == today,
            }
        )
    return templates.TemplateResponse(
        "timesheets.html",
        {
            "request": request,
            "user": current_user,
            "total_hours": approved_hours,
            "entry_count": entry_count,
            "recent_entries": recent_entries,
            "projects": project_options,
            "tasks": task_options,
            "day_statuses": day_statuses,
            "week_start": week_start,
            "week_end": week_end,
            "week_summary": current_week,
            "error": None,
            "today": today,
        },
    )


@app.post("/timesheets/form")
def create_timesheet_form(
    entry_date: date = Form(...),
    hours: float = Form(...),
    description: str = Form(...),
    project_id: str | None = Form(None),
    task_id: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if hours <= 0 or hours > 24:
        raise HTTPException(status_code=400, detail="Hours must be between 0 and 24")
    week_start, week_end = week_bounds(entry_date)
    summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == current_user.id,
            TimesheetWeekSummary.week_start == week_start,
        )
    )
    if summary and summary.status == TimesheetWeekStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Approved timesheets cannot be edited.")
    parsed_project_id = parse_optional_int(project_id)
    parsed_task_id = parse_optional_int(task_id)
    entry = TimesheetEntry(
        user_id=current_user.id,
        project_id=parsed_project_id,
        task_id=parsed_task_id,
        entry_date=entry_date,
        hours=hours,
        description=description,
    )
    db.add(entry)
    db.flush()
    db.add(
        TimesheetEntryAudit(
            entry_id=entry.id,
            actor_id=current_user.id,
            action="created",
            field_name="entry",
            old_value="",
            new_value=f"{entry.entry_date} ({entry.hours}h)",
        )
    )
    if parsed_task_id:
        task = db.get(Task, parsed_task_id)
        if task:
            task.logged_hours += hours
    db.commit()
    return RedirectResponse("/timesheets", status_code=303)


@app.post("/timesheets/{entry_id}/edit")
def edit_timesheet_form(
    entry_id: int,
    entry_date: date = Form(...),
    hours: float = Form(...),
    description: str = Form(...),
    project_id: str | None = Form(None),
    task_id: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.get(TimesheetEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Timesheet entry not found.")
    original_week_start, _ = week_bounds(entry.entry_date)
    original_summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == current_user.id,
            TimesheetWeekSummary.week_start == original_week_start,
        )
    )
    if original_summary and original_summary.status == TimesheetWeekStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Approved timesheets cannot be edited.")
    new_week_start, _ = week_bounds(entry_date)
    if new_week_start != original_week_start:
        new_summary = db.scalar(
            select(TimesheetWeekSummary).where(
                TimesheetWeekSummary.user_id == current_user.id,
                TimesheetWeekSummary.week_start == new_week_start,
            )
        )
        if new_summary and new_summary.status == TimesheetWeekStatus.APPROVED:
            raise HTTPException(status_code=400, detail="Approved timesheets cannot be edited.")
    parsed_project_id = parse_optional_int(project_id)
    parsed_task_id = parse_optional_int(task_id)
    changes = []
    if entry.entry_date != entry_date:
        changes.append(("entry_date", str(entry.entry_date), str(entry_date)))
        entry.entry_date = entry_date
    if entry.hours != hours:
        changes.append(("hours", str(entry.hours), str(hours)))
        entry.hours = hours
    if entry.description != description:
        changes.append(("description", entry.description, description))
        entry.description = description
    if entry.project_id != parsed_project_id:
        changes.append(("project_id", str(entry.project_id or ""), str(parsed_project_id or "")))
        entry.project_id = parsed_project_id
    if entry.task_id != parsed_task_id:
        changes.append(("task_id", str(entry.task_id or ""), str(parsed_task_id or "")))
        entry.task_id = parsed_task_id
    entry.updated_at = datetime.utcnow()
    for field_name, old_value, new_value in changes:
        db.add(
            TimesheetEntryAudit(
                entry_id=entry.id,
                actor_id=current_user.id,
                action="edited",
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
        )
    db.commit()
    return RedirectResponse("/timesheets", status_code=303)


@app.post("/timesheets/submit-week")
def submit_timesheet_week(
    week_start: date = Form(...),
    submit_note: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    week_end = week_start + timedelta(days=6)
    summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == current_user.id,
            TimesheetWeekSummary.week_start == week_start,
        )
    )
    if not summary:
        summary = TimesheetWeekSummary(
            user_id=current_user.id,
            week_start=week_start,
            week_end=week_end,
        )
        db.add(summary)
    if summary.status == TimesheetWeekStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Approved timesheets cannot be resubmitted.")
    summary.status = TimesheetWeekStatus.SUBMITTED
    summary.submit_note = submit_note
    summary.submitted_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/timesheets", status_code=303)


@app.post("/timesheets/unsubmit-week")
def unsubmit_timesheet_week(
    week_start: date = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == current_user.id,
            TimesheetWeekSummary.week_start == week_start,
        )
    )
    if not summary:
        raise HTTPException(status_code=404, detail="Timesheet week not found.")
    if summary.status == TimesheetWeekStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Approved timesheets cannot be unsubmitted.")
    summary.status = TimesheetWeekStatus.DRAFT
    summary.submit_note = ""
    summary.submitted_at = None
    db.commit()
    return RedirectResponse("/timesheets", status_code=303)


@app.post("/timesheets/approve-week")
def approve_timesheet_week(
    week_start: date = Form(...),
    user_id: int = Form(...),
    approval_note: str = Form(""),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.week_start == week_start,
            TimesheetWeekSummary.user_id == user_id,
        )
    )
    if not summary:
        raise HTTPException(status_code=404, detail="Timesheet week not found.")
    if summary.status != TimesheetWeekStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Timesheet must be submitted before approval.")
    target_user = db.get(User, summary.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Timesheet owner not found.")
    if actor.role != Role.ADMIN and target_user.manager_id != actor.id:
        raise HTTPException(status_code=403, detail="Only the line manager can approve this timesheet.")
    summary.status = TimesheetWeekStatus.APPROVED
    summary.approver_id = actor.id
    summary.approval_note = approval_note
    summary.approved_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/timesheets", status_code=303)


@app.post("/timesheets/unapprove-week")
def unapprove_timesheet_week(
    week_start: date = Form(...),
    user_id: int = Form(...),
    approval_note: str = Form(""),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.week_start == week_start,
            TimesheetWeekSummary.user_id == user_id,
        )
    )
    if not summary:
        raise HTTPException(status_code=404, detail="Timesheet week not found.")
    if summary.status != TimesheetWeekStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved timesheets can be unapproved.")
    target_user = db.get(User, summary.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Timesheet owner not found.")
    if actor.role != Role.ADMIN and target_user.manager_id != actor.id:
        raise HTTPException(status_code=403, detail="Only the line manager can unapprove this timesheet.")
    summary.status = TimesheetWeekStatus.SUBMITTED
    summary.approval_note = approval_note
    summary.approved_at = None
    summary.approver_id = None
    db.commit()
    return RedirectResponse("/timesheets", status_code=303)


@app.get("/leave-requests", response_class=HTMLResponse)
def leave_requests(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    my_requests = db.scalar(select(func.count(LeaveRequest.id)).where(LeaveRequest.user_id == current_user.id)) or 0
    my_pending = db.scalar(
        select(func.count(LeaveRequest.id)).where(LeaveRequest.user_id == current_user.id, LeaveRequest.status == LeaveStatus.PENDING)
    ) or 0
    recent_leave = db.scalars(
        select(LeaveRequest).where(LeaveRequest.user_id == current_user.id).order_by(LeaveRequest.start_date.desc()).limit(5)
    ).all()
    pending_query = select(LeaveRequest).options(selectinload(LeaveRequest.user)).where(LeaveRequest.status == LeaveStatus.PENDING)
    if current_user.role != Role.ADMIN:
        pending_query = pending_query.join(User, LeaveRequest.user_id == User.id).where(User.manager_id == current_user.id)
    pending_approvals = db.scalars(pending_query.limit(5)).all()
    return templates.TemplateResponse(
        "leave_requests.html",
        {
            "request": request,
            "user": current_user,
            "my_requests": my_requests,
            "my_pending": my_pending,
            "recent_leave": recent_leave,
            "pending_approvals": pending_approvals,
        },
    )


@app.post("/leave-requests/form")
def request_leave_form(
    start_date: date = Form(...),
    end_date: date = Form(...),
    reason: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")
    leave = LeaveRequest(user_id=current_user.id, start_date=start_date, end_date=end_date, reason=reason)
    db.add(leave)
    db.commit()
    return RedirectResponse("/leave-requests", status_code=303)


@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_projects = db.scalar(select(func.count(Project.id))) or 0
    active_projects = db.scalar(select(func.count(Project.id)).where(Project.status != "completed")) or 0
    recent_projects = db.scalars(select(Project).order_by(Project.id.desc()).limit(6)).all()
    programmes = db.scalars(select(Programme).order_by(Programme.name.asc())).all()
    managers = db.scalars(select(User).order_by(User.full_name.asc())).all()
    customers = db.scalars(select(Customer).order_by(Customer.name.asc())).all()
    return templates.TemplateResponse(
        "projects.html",
        {
            "request": request,
            "user": current_user,
            "total_projects": total_projects,
            "active_projects": active_projects,
            "recent_projects": recent_projects,
            "programmes": programmes,
            "managers": managers,
            "customers": customers,
            "error": None,
        },
    )


@app.post("/projects/form")
def create_project_form(
    name: str = Form(...),
    description: str = Form(...),
    customer_id: str = Form(...),
    programme_id: str | None = Form(None),
    manager_id: str | None = Form(None),
    planned_hours: str | None = Form("0"),
    planned_material_budget: str | None = Form("0"),
    planned_subcontract_budget: str | None = Form("0"),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    parsed_customer_id = parse_optional_int(customer_id)
    if not parsed_customer_id:
        raise HTTPException(status_code=400, detail="Projects require a customer.")
    project = Project(
        name=name,
        description=description,
        customer_id=parsed_customer_id,
        programme_id=parse_optional_int(programme_id),
        manager_id=parse_optional_int(manager_id),
        planned_hours=parse_optional_float(planned_hours, field_label="planned hours") or 0,
        planned_material_budget=parse_optional_float(planned_material_budget, field_label="material budget") or 0,
        planned_subcontract_budget=parse_optional_float(planned_subcontract_budget, field_label="subcontract budget") or 0,
    )
    db.add(project)
    db.commit()
    return RedirectResponse("/projects", status_code=303)


@app.get("/programmes", response_class=HTMLResponse)
def programmes(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    programme_count = db.scalar(select(func.count(Programme.id))) or 0
    managed_programmes = db.scalar(select(func.count(Programme.id)).where(Programme.manager_id.is_not(None))) or 0
    recent_programmes = db.scalars(select(Programme).order_by(Programme.id.desc()).limit(6)).all()
    managers = db.scalars(select(User).order_by(User.full_name.asc())).all()
    return templates.TemplateResponse(
        "programmes.html",
        {
            "request": request,
            "user": current_user,
            "programme_count": programme_count,
            "managed_programmes": managed_programmes,
            "recent_programmes": recent_programmes,
            "managers": managers,
            "error": None,
        },
    )


@app.get("/customers", response_class=HTMLResponse)
def customers(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer_count = db.scalar(select(func.count(Customer.id))) or 0
    recent_customers = db.scalars(select(Customer).order_by(Customer.created_at.desc()).limit(8)).all()
    return templates.TemplateResponse(
        "customers.html",
        {
            "request": request,
            "user": current_user,
            "customer_count": customer_count,
            "recent_customers": recent_customers,
            "error": None,
        },
    )


@app.post("/customers/form")
def create_customer_form(
    name: str = Form(...),
    industry: str = Form(""),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    customer = Customer(name=name, industry=industry)
    db.add(customer)
    db.commit()
    return RedirectResponse("/customers", status_code=303)


@app.post("/customers/{customer_id}/delete")
def delete_customer_form(
    customer_id: int,
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER)),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    db.delete(customer)
    db.commit()
    return RedirectResponse("/customers", status_code=303)


@app.post("/programmes/form")
def create_programme_form(
    name: str = Form(...),
    description: str = Form(...),
    manager_id: str | None = Form(None),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER)),
    db: Session = Depends(get_db),
):
    programme = Programme(name=name, description=description, manager_id=parse_optional_int(manager_id))
    db.add(programme)
    db.commit()
    return RedirectResponse("/programmes", status_code=303)


@app.get("/company", response_class=HTMLResponse)
def company(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_count = db.scalar(select(func.count(User.id))) or 0
    admin_count = db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN)) or 0
    tier_count = db.scalar(select(func.count(SubscriptionTier.id))) or 0
    config_count = db.scalar(select(func.count(AppConfig.id))) or 0
    recent_users = db.scalars(select(User).order_by(User.created_at.desc()).limit(6)).all()
    users = db.scalars(select(User).order_by(User.full_name.asc())).all()
    defaults = default_working_hours(db)
    pending_timesheets_query = select(TimesheetWeekSummary).options(selectinload(TimesheetWeekSummary.user)).where(
        TimesheetWeekSummary.status.in_([TimesheetWeekStatus.SUBMITTED, TimesheetWeekStatus.APPROVED])
    )
    if current_user.role != Role.ADMIN:
        pending_timesheets_query = pending_timesheets_query.join(User, TimesheetWeekSummary.user_id == User.id).where(User.manager_id == current_user.id)
    pending_timesheets = db.scalars(pending_timesheets_query.order_by(TimesheetWeekSummary.week_start.desc()).limit(6)).all()
    return templates.TemplateResponse(
        "company.html",
        {
            "request": request,
            "user": current_user,
            "user_count": user_count,
            "admin_count": admin_count,
            "tier_count": tier_count,
            "config_count": config_count,
            "recent_users": recent_users,
            "users": users,
            "defaults": defaults,
            "pending_timesheets": pending_timesheets,
            "error": None,
        },
    )


@app.post("/company/users/create")
def create_company_user(
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: Role = Form(...),
    manager_id: str | None = Form(None),
    leave_entitlement_days: str | None = Form("25"),
    working_hours_mon: str | None = Form(""),
    working_hours_tue: str | None = Form(""),
    working_hours_wed: str | None = Form(""),
    working_hours_thu: str | None = Form(""),
    working_hours_fri: str | None = Form(""),
    working_hours_sat: str | None = Form(""),
    working_hours_sun: str | None = Form(""),
    actor: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    defaults = default_working_hours(db)
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
        manager_id=parse_optional_int(manager_id),
        leave_entitlement_days=parse_optional_float(leave_entitlement_days, field_label="leave entitlement") or 25,
        working_hours_mon=parse_optional_float(working_hours_mon, field_label="Monday hours") or defaults["mon"],
        working_hours_tue=parse_optional_float(working_hours_tue, field_label="Tuesday hours") or defaults["tue"],
        working_hours_wed=parse_optional_float(working_hours_wed, field_label="Wednesday hours") or defaults["wed"],
        working_hours_thu=parse_optional_float(working_hours_thu, field_label="Thursday hours") or defaults["thu"],
        working_hours_fri=parse_optional_float(working_hours_fri, field_label="Friday hours") or defaults["fri"],
        working_hours_sat=parse_optional_float(working_hours_sat, field_label="Saturday hours") or defaults["sat"],
        working_hours_sun=parse_optional_float(working_hours_sun, field_label="Sunday hours") or defaults["sun"],
    )
    db.add(user)
    db.commit()
    return RedirectResponse("/company", status_code=303)


@app.post("/company/users/update")
def update_company_user(
    user_id: int = Form(...),
    manager_id: str | None = Form(None),
    leave_entitlement_days: str | None = Form(""),
    working_hours_mon: str | None = Form(""),
    working_hours_tue: str | None = Form(""),
    working_hours_wed: str | None = Form(""),
    working_hours_thu: str | None = Form(""),
    working_hours_fri: str | None = Form(""),
    working_hours_sat: str | None = Form(""),
    working_hours_sun: str | None = Form(""),
    actor: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.manager_id = parse_optional_int(manager_id)
    user.leave_entitlement_days = parse_optional_float(leave_entitlement_days, field_label="leave entitlement") or user.leave_entitlement_days
    user.working_hours_mon = parse_optional_float(working_hours_mon, field_label="Monday hours") or user.working_hours_mon
    user.working_hours_tue = parse_optional_float(working_hours_tue, field_label="Tuesday hours") or user.working_hours_tue
    user.working_hours_wed = parse_optional_float(working_hours_wed, field_label="Wednesday hours") or user.working_hours_wed
    user.working_hours_thu = parse_optional_float(working_hours_thu, field_label="Thursday hours") or user.working_hours_thu
    user.working_hours_fri = parse_optional_float(working_hours_fri, field_label="Friday hours") or user.working_hours_fri
    user.working_hours_sat = parse_optional_float(working_hours_sat, field_label="Saturday hours") or user.working_hours_sat
    user.working_hours_sun = parse_optional_float(working_hours_sun, field_label="Sunday hours") or user.working_hours_sun
    db.commit()
    return RedirectResponse("/company", status_code=303)


@app.post("/company/users/toggle-active")
def toggle_company_user(
    user_id: int = Form(...),
    actor: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role == Role.ADMIN and user.id == actor.id:
        raise HTTPException(status_code=400, detail="Admins cannot deactivate themselves.")
    user.active = not user.active
    db.commit()
    return RedirectResponse("/company", status_code=303)


@app.post("/company/defaults")
def update_company_defaults(
    default_hours_mon: str = Form(...),
    default_hours_tue: str = Form(...),
    default_hours_wed: str = Form(...),
    default_hours_thu: str = Form(...),
    default_hours_fri: str = Form(...),
    default_hours_sat: str = Form(...),
    default_hours_sun: str = Form(...),
    actor: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    defaults = {
        "default_hours_mon": parse_optional_float(default_hours_mon, field_label="Monday default") or 0,
        "default_hours_tue": parse_optional_float(default_hours_tue, field_label="Tuesday default") or 0,
        "default_hours_wed": parse_optional_float(default_hours_wed, field_label="Wednesday default") or 0,
        "default_hours_thu": parse_optional_float(default_hours_thu, field_label="Thursday default") or 0,
        "default_hours_fri": parse_optional_float(default_hours_fri, field_label="Friday default") or 0,
        "default_hours_sat": parse_optional_float(default_hours_sat, field_label="Saturday default") or 0,
        "default_hours_sun": parse_optional_float(default_hours_sun, field_label="Sunday default") or 0,
    }
    for key, value in defaults.items():
        config = db.scalar(select(AppConfig).where(AppConfig.key == key))
        if config:
            config.value = str(value)
        else:
            db.add(AppConfig(key=key, value=str(value)))
    db.commit()
    return RedirectResponse("/company", status_code=303)


@app.get("/site-management", response_class=HTMLResponse)
def site_management(request: Request, current_user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    tier_count = db.scalar(select(func.count(SubscriptionTier.id))) or 0
    config_count = db.scalar(select(func.count(AppConfig.id))) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.active.is_(True))) or 0
    subscription_tiers = db.scalars(select(SubscriptionTier).order_by(SubscriptionTier.monthly_price.desc())).all()
    configs = db.scalars(select(AppConfig).order_by(AppConfig.key.asc()).limit(8)).all()
    return templates.TemplateResponse(
        "site_management.html",
        {
            "request": request,
            "user": current_user,
            "tier_count": tier_count,
            "config_count": config_count,
            "active_users": active_users,
            "subscription_tiers": subscription_tiers,
            "configs": configs,
        },
    )


@app.get("/learning-zone", response_class=HTMLResponse)
def learning_zone(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "learning_zone.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.get("/subscription", response_class=HTMLResponse)
def subscription(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "subscription.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, current_user: User = Depends(require_roles(Role.ADMIN))):
    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.get("/admin/site", response_class=HTMLResponse)
def admin_site(request: Request, current_user: User = Depends(require_roles(Role.ADMIN))):
    return templates.TemplateResponse(
        "admin_site.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.post("/users")
def create_user(payload: UserCreate, actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    if not can_manage_target(actor, payload.role):
        raise HTTPException(status_code=403, detail="Role not permitted")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        cost_rate=payload.cost_rate,
        bill_rate=payload.bill_rate,
        manager_id=payload.manager_id,
        leave_entitlement_days=payload.leave_entitlement_days,
        working_hours_mon=payload.working_hours_mon,
        working_hours_tue=payload.working_hours_tue,
        working_hours_wed=payload.working_hours_wed,
        working_hours_thu=payload.working_hours_thu,
        working_hours_fri=payload.working_hours_fri,
        working_hours_sat=payload.working_hours_sat,
        working_hours_sun=payload.working_hours_sun,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    target_role = payload.role or user.role
    if not can_manage_target(actor, target_role):
        raise HTTPException(status_code=403, detail="Role not permitted")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: int, actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not can_manage_target(actor, user.role):
        raise HTTPException(status_code=403, detail="Role not permitted")
    db.delete(user)
    db.commit()
    return {"ok": True}


@app.post("/projects")
def create_project(payload: ProjectCreate, actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    if not payload.customer_id:
        raise HTTPException(status_code=400, detail="Projects require a customer.")
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.post("/projects/{project_id}/work-packages")
def create_work_package(project_id: int, name: str = Form(...), description: str = Form(""), actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    wp = WorkPackage(project_id=project_id, name=name, description=description)
    db.add(wp)
    db.commit()
    return {"ok": True, "id": wp.id}


@app.post("/work-packages/{work_package_id}/tasks")
def create_task(work_package_id: int, name: str = Form(...), description: str = Form(""), planned_hours: float = Form(0), actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    task = Task(work_package_id=work_package_id, name=name, description=description, planned_hours=planned_hours)
    db.add(task)
    db.commit()
    return {"ok": True, "id": task.id}


@app.post("/projects/{project_id}/resource-requirements")
def create_resource_requirement(project_id: int, resource_type: str = Form(...), notes: str = Form(""), required_hours: float = Form(0), planned_cost: float = Form(0), actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)), db: Session = Depends(get_db)):
    requirement = ResourceRequirement(project_id=project_id, resource_type=resource_type, notes=notes, required_hours=required_hours, planned_cost=planned_cost)
    db.add(requirement)
    db.commit()
    return {"ok": True}


@app.post("/timesheets")
def create_timesheet(payload: TimesheetCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    week_start, _ = week_bounds(payload.entry_date)
    summary = db.scalar(
        select(TimesheetWeekSummary).where(
            TimesheetWeekSummary.user_id == current_user.id,
            TimesheetWeekSummary.week_start == week_start,
        )
    )
    if summary and summary.status == TimesheetWeekStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Approved timesheets cannot be edited.")
    entry = TimesheetEntry(user_id=current_user.id, **payload.model_dump())
    db.add(entry)
    db.flush()
    db.add(
        TimesheetEntryAudit(
            entry_id=entry.id,
            actor_id=current_user.id,
            action="created",
            field_name="entry",
            old_value="",
            new_value=f"{entry.entry_date} ({entry.hours}h)",
        )
    )
    if payload.task_id:
        task = db.get(Task, payload.task_id)
        if task:
            task.logged_hours += payload.hours
    db.commit()
    return {"ok": True}


@app.post("/leave-requests")
def request_leave(payload: LeaveCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    leave = LeaveRequest(user_id=current_user.id, **payload.model_dump())
    db.add(leave)
    db.commit()
    return {"ok": True}


@app.post("/leave-requests/{request_id}/decision")
def decide_leave(
    request_id: int,
    approve: bool = Form(...),
    current_user: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    leave = db.get(LeaveRequest, request_id)
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    target_user = db.get(User, leave.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Leave request owner not found")
    if current_user.role != Role.ADMIN and target_user.manager_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the line manager can approve this leave.")
    leave.status = LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED
    leave.reviewer_id = current_user.id
    db.commit()
    return {"ok": True}


@app.post("/sick-leave")
def report_sick_leave(payload: SickLeaveCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = SickLeaveRecord(user_id=current_user.id, **payload.model_dump())
    db.add(record)
    db.commit()
    return {"ok": True}


@app.post("/subscription-tiers")
def create_subscription_tier(name: str = Form(...), monthly_price: float = Form(...), features: str = Form(""), stripe_price_id: str | None = Form(None), current_user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    tier = SubscriptionTier(name=name, monthly_price=monthly_price, features=features, stripe_price_id=stripe_price_id)
    db.add(tier)
    db.commit()
    return {"ok": True}


@app.post("/admin/site-config")
def upsert_site_config(key: str = Form(...), value: str = Form(...), current_user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    config = db.scalar(select(AppConfig).where(AppConfig.key == key))
    if config:
        config.value = value
    else:
        db.add(AppConfig(key=key, value=value))
    db.commit()
    return {"ok": True}


@app.get("/health")
def healthcheck():
    return {"status": "ok", "date": date.today().isoformat()}
