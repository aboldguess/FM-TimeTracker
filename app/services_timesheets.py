"""Timesheet domain helpers.

This module contains pure business-logic helpers for timesheet behavior,
including safe task logged-hour balancing during timesheet entry edits.
"""

from app.models import Task


def apply_task_logged_hours_edit(
    *,
    old_task: Task | None,
    new_task: Task | None,
    old_hours: float,
    new_hours: float,
) -> None:
    """Apply task logged-hour updates for a timesheet edit safely.

    Rules:
    - same task: apply only the delta (new - old)
    - reassigned task: subtract old hours from old task and add new hours to new task
    - add/remove task link: update only the task that is present

    Any subtraction is clamped at zero to avoid negative logged totals.
    """
    if old_task and new_task and old_task.id == new_task.id:
        delta = new_hours - old_hours
        old_task.logged_hours = max(old_task.logged_hours + delta, 0.0)
        return

    if old_task:
        old_task.logged_hours = max(old_task.logged_hours - old_hours, 0.0)
    if new_task:
        new_task.logged_hours += new_hours
