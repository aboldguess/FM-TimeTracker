"""ORM models.

Defines secure role-based user accounts, customer/project/programme hierarchy,
resource planning and tracking records, timesheet/leave management, and
subscription/payment-related entities with auditable change history.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(str, Enum):
    ADMIN = "admin"
    PROGRAMME_MANAGER = "programme_manager"
    PROJECT_MANAGER = "project_manager"
    STAFF = "staff"


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TimesheetWeekStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SQLEnum(Role), default=Role.STAFF)
    profile_image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    cost_rate: Mapped[float] = mapped_column(Float, default=0)
    bill_rate: Mapped[float] = mapped_column(Float, default=0)
    leave_entitlement_days: Mapped[float] = mapped_column(Float, default=25)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    working_hours_mon: Mapped[float] = mapped_column(Float, default=8)
    working_hours_tue: Mapped[float] = mapped_column(Float, default=8)
    working_hours_wed: Mapped[float] = mapped_column(Float, default=8)
    working_hours_thu: Mapped[float] = mapped_column(Float, default=8)
    working_hours_fri: Mapped[float] = mapped_column(Float, default=8)
    working_hours_sat: Mapped[float] = mapped_column(Float, default=0)
    working_hours_sun: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    timesheets: Mapped[list[TimesheetEntry]] = relationship(back_populates="user", cascade="all, delete-orphan")
    timesheet_weeks: Mapped[list[TimesheetWeekSummary]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="TimesheetWeekSummary.user_id",
    )
    timesheet_audits: Mapped[list[TimesheetEntryAudit]] = relationship(
        back_populates="actor",
        cascade="all, delete-orphan",
        foreign_keys="TimesheetEntryAudit.actor_id",
    )
    manager: Mapped[User | None] = relationship(remote_side="User.id")
    leave_requests: Mapped[list[LeaveRequest]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="LeaveRequest.user_id",
    )
    reviewed_leave_requests: Mapped[list[LeaveRequest]] = relationship(
        back_populates="reviewer",
        foreign_keys="LeaveRequest.reviewer_id",
    )
    sick_leaves: Mapped[list[SickLeaveRecord]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Programme(Base):
    __tablename__ = "programmes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    projects: Mapped[list[Project]] = relationship(back_populates="programme", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    programme_id: Mapped[int | None] = mapped_column(ForeignKey("programmes.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(140), unique=True)
    description: Mapped[str] = mapped_column(Text)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="planned")
    planned_hours: Mapped[float] = mapped_column(Float, default=0)
    planned_material_budget: Mapped[float] = mapped_column(Float, default=0)
    planned_subcontract_budget: Mapped[float] = mapped_column(Float, default=0)
    progress_percent: Mapped[float] = mapped_column(Float, default=0)

    customer: Mapped[Customer | None] = relationship(back_populates="projects")
    programme: Mapped[Programme | None] = relationship(back_populates="projects")
    work_packages: Mapped[list[WorkPackage]] = relationship(back_populates="project", cascade="all, delete-orphan")
    resource_requirements: Mapped[list[ResourceRequirement]] = relationship(back_populates="project", cascade="all, delete-orphan")


class WorkPackage(Base):
    __tablename__ = "work_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    progress_percent: Mapped[float] = mapped_column(Float, default=0)

    project: Mapped[Project] = relationship(back_populates="work_packages")
    tasks: Mapped[list[Task]] = relationship(back_populates="work_package", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_package_id: Mapped[int] = mapped_column(ForeignKey("work_packages.id"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    planned_hours: Mapped[float] = mapped_column(Float, default=0)
    logged_hours: Mapped[float] = mapped_column(Float, default=0)
    progress_percent: Mapped[float] = mapped_column(Float, default=0)

    work_package: Mapped[WorkPackage] = relationship(back_populates="tasks")


class ResourceRequirement(Base):
    __tablename__ = "resource_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    resource_type: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str] = mapped_column(Text, default="")
    required_hours: Mapped[float] = mapped_column(Float, default=0)
    planned_cost: Mapped[float] = mapped_column(Float, default=0)

    project: Mapped[Project] = relationship(back_populates="resource_requirements")


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today)
    hours: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="timesheets")
    audits: Mapped[list[TimesheetEntryAudit]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[LeaveStatus] = mapped_column(SQLEnum(LeaveStatus), default=LeaveStatus.PENDING)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped[User] = relationship(back_populates="leave_requests", foreign_keys=[user_id])
    reviewer: Mapped[User | None] = relationship(
        back_populates="reviewed_leave_requests",
        foreign_keys=[reviewer_id],
    )


class SickLeaveRecord(Base):
    __tablename__ = "sick_leave_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(back_populates="sick_leaves")


class SubscriptionTier(Base):
    __tablename__ = "subscription_tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    monthly_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    stripe_price_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    features: Mapped[str] = mapped_column(Text, default="")


class AppConfig(Base):
    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    value: Mapped[str] = mapped_column(Text)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), unique=True)
    industry: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list[Project]] = relationship(back_populates="customer")


class TimesheetWeekSummary(Base):
    __tablename__ = "timesheet_week_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    week_start: Mapped[date] = mapped_column(Date, index=True)
    week_end: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[TimesheetWeekStatus] = mapped_column(SQLEnum(TimesheetWeekStatus), default=TimesheetWeekStatus.DRAFT)
    submit_note: Mapped[str] = mapped_column(Text, default="")
    approval_note: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped[User] = relationship(back_populates="timesheet_weeks", foreign_keys=[user_id])
    approver: Mapped[User | None] = relationship(foreign_keys=[approver_id])


class TimesheetEntryAudit(Base):
    __tablename__ = "timesheet_entry_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("timesheet_entries.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    field_name: Mapped[str] = mapped_column(String(120), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entry: Mapped[TimesheetEntry] = relationship(back_populates="audits")
    actor: Mapped[User] = relationship(back_populates="timesheet_audits", foreign_keys=[actor_id])
