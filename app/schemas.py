"""Pydantic schemas.

Defines validation for incoming payloads to keep endpoints safe and explicit,
including line management and working-hour inputs.
"""

from datetime import date

from pydantic import BaseModel, EmailStr, Field

from app.models import Role


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10)
    role: Role
    cost_rate: float = 0
    bill_rate: float = 0
    manager_id: int | None = None
    leave_entitlement_days: float = 25
    working_hours_mon: float = 8
    working_hours_tue: float = 8
    working_hours_wed: float = 8
    working_hours_thu: float = 8
    working_hours_fri: float = 8
    working_hours_sat: float = 0
    working_hours_sun: float = 0


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    cost_rate: float | None = None
    bill_rate: float | None = None
    leave_entitlement_days: float | None = None
    manager_id: int | None = None
    working_hours_mon: float | None = None
    working_hours_tue: float | None = None
    working_hours_wed: float | None = None
    working_hours_thu: float | None = None
    working_hours_fri: float | None = None
    working_hours_sat: float | None = None
    working_hours_sun: float | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProjectCreate(BaseModel):
    name: str
    description: str
    customer_id: int | None = None
    programme_id: int | None = None
    manager_id: int | None = None
    planned_hours: float = 0
    planned_material_budget: float = 0
    planned_subcontract_budget: float = 0


class TimesheetCreate(BaseModel):
    project_id: int | None = None
    task_id: int | None = None
    entry_date: date
    hours: float = Field(gt=0, le=24)
    description: str


class LeaveCreate(BaseModel):
    start_date: date
    end_date: date
    reason: str


class SickLeaveCreate(BaseModel):
    start_date: date
    end_date: date
    notes: str = ""
