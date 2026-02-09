"""Application entrypoint.

This file wires API routes, HTML pages, RBAC enforcement, and startup actions
for the FM TimeTracker browser application.
"""

from datetime import date

import stripe
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import Base, engine, get_db
from app.dependencies import can_manage_target, get_current_user, require_roles
from app.models import (
    AppConfig,
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
    User,
    WorkPackage,
)
from app.schemas import LeaveCreate, LoginRequest, ProjectCreate, SickLeaveCreate, TimesheetCreate, UserCreate, UserUpdate
from app.security import create_session_token, ensure_password_backend, hash_password, verify_password

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


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
    Base.metadata.create_all(bind=engine)
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
    timesheet_hours = db.scalar(select(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).where(TimesheetEntry.user_id == current_user.id))
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
    total_hours = db.scalar(select(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).where(TimesheetEntry.user_id == current_user.id))
    entry_count = db.scalar(select(func.count(TimesheetEntry.id)).where(TimesheetEntry.user_id == current_user.id)) or 0
    recent_entries = db.scalars(
        select(TimesheetEntry).where(TimesheetEntry.user_id == current_user.id).order_by(TimesheetEntry.entry_date.desc()).limit(6)
    ).all()
    return templates.TemplateResponse(
        "timesheets.html",
        {
            "request": request,
            "user": current_user,
            "total_hours": total_hours,
            "entry_count": entry_count,
            "recent_entries": recent_entries,
        },
    )


@app.post("/timesheets/form")
def create_timesheet_form(
    entry_date: date = Form(...),
    hours: float = Form(...),
    description: str = Form(...),
    project_id: int | None = Form(None),
    task_id: int | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if hours <= 0 or hours > 24:
        raise HTTPException(status_code=400, detail="Hours must be between 0 and 24")
    entry = TimesheetEntry(
        user_id=current_user.id,
        project_id=project_id,
        task_id=task_id,
        entry_date=entry_date,
        hours=hours,
        description=description,
    )
    db.add(entry)
    if task_id:
        task = db.get(Task, task_id)
        if task:
            task.logged_hours += hours
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
    pending_approvals = db.scalars(
        select(LeaveRequest).options(selectinload(LeaveRequest.user)).where(LeaveRequest.status == LeaveStatus.PENDING).limit(5)
    ).all()
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
    return templates.TemplateResponse(
        "projects.html",
        {
            "request": request,
            "user": current_user,
            "total_projects": total_projects,
            "active_projects": active_projects,
            "recent_projects": recent_projects,
        },
    )


@app.post("/projects/form")
def create_project_form(
    name: str = Form(...),
    description: str = Form(...),
    programme_id: int | None = Form(None),
    manager_id: int | None = Form(None),
    planned_hours: float = Form(0),
    planned_material_budget: float = Form(0),
    planned_subcontract_budget: float = Form(0),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    project = Project(
        name=name,
        description=description,
        programme_id=programme_id,
        manager_id=manager_id,
        planned_hours=planned_hours,
        planned_material_budget=planned_material_budget,
        planned_subcontract_budget=planned_subcontract_budget,
    )
    db.add(project)
    db.commit()
    return RedirectResponse("/projects", status_code=303)


@app.get("/programmes", response_class=HTMLResponse)
def programmes(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    programme_count = db.scalar(select(func.count(Programme.id))) or 0
    managed_programmes = db.scalar(select(func.count(Programme.id)).where(Programme.manager_id.is_not(None))) or 0
    recent_programmes = db.scalars(select(Programme).order_by(Programme.id.desc()).limit(6)).all()
    return templates.TemplateResponse(
        "programmes.html",
        {
            "request": request,
            "user": current_user,
            "programme_count": programme_count,
            "managed_programmes": managed_programmes,
            "recent_programmes": recent_programmes,
        },
    )


@app.post("/programmes/form")
def create_programme_form(
    name: str = Form(...),
    description: str = Form(...),
    manager_id: int | None = Form(None),
    actor: User = Depends(require_roles(Role.ADMIN, Role.PROGRAMME_MANAGER)),
    db: Session = Depends(get_db),
):
    programme = Programme(name=name, description=description, manager_id=manager_id)
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
        },
    )


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
    entry = TimesheetEntry(user_id=current_user.id, **payload.model_dump())
    db.add(entry)
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
def decide_leave(request_id: int, approve: bool = Form(...), current_user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    leave = db.get(LeaveRequest, request_id)
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
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
