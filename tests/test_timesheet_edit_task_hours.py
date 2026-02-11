"""Mini-README: Regression tests for task logged-hour balancing on timesheet edits.

These tests cover same-task edits, task reassignments, and task add/remove
transitions to ensure task.logged_hours stays correct and never goes negative.
"""

from dataclasses import dataclass

from app.services_timesheets import apply_task_logged_hours_edit


@dataclass
class FakeTask:
    """Simple stand-in for Task objects used by the balancing helper."""

    id: int
    logged_hours: float


def test_apply_task_logged_hours_edit_same_task_uses_delta() -> None:
    task = FakeTask(id=10, logged_hours=7.5)

    apply_task_logged_hours_edit(old_task=task, new_task=task, old_hours=2.5, new_hours=5.0)

    assert task.logged_hours == 10.0


def test_apply_task_logged_hours_edit_task_reassignment_moves_hours() -> None:
    old_task = FakeTask(id=10, logged_hours=8.0)
    new_task = FakeTask(id=11, logged_hours=1.0)

    apply_task_logged_hours_edit(old_task=old_task, new_task=new_task, old_hours=3.0, new_hours=4.5)

    assert old_task.logged_hours == 5.0
    assert new_task.logged_hours == 5.5


def test_apply_task_logged_hours_edit_task_removed_clamps_at_zero() -> None:
    old_task = FakeTask(id=10, logged_hours=1.0)

    apply_task_logged_hours_edit(old_task=old_task, new_task=None, old_hours=3.0, new_hours=0.0)

    assert old_task.logged_hours == 0.0


def test_apply_task_logged_hours_edit_task_added_increases_new_task() -> None:
    new_task = FakeTask(id=11, logged_hours=1.25)

    apply_task_logged_hours_edit(old_task=None, new_task=new_task, old_hours=0.0, new_hours=2.75)

    assert new_task.logged_hours == 4.0
