"""Add created_at and updated_at to timesheet entries.

This migration is intentionally idempotent for legacy SQLite databases that may
already include one or both columns from manual schema creation.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "64b8f8ccdf7c"
down_revision: Union[str, None] = "17ed833d2e37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns_for_timesheet_entries() -> set[str]:
    """Return the current set of column names for timesheet_entries."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("timesheet_entries")}


def upgrade() -> None:
    """Add audit timestamp columns used for safer operational tracing."""
    existing_columns = _columns_for_timesheet_entries()

    with op.batch_alter_table("timesheet_entries") as batch_op:
        if "created_at" not in existing_columns:
            batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        if "updated_at" not in existing_columns:
            batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove timesheet timestamp columns if present."""
    existing_columns = _columns_for_timesheet_entries()

    with op.batch_alter_table("timesheet_entries") as batch_op:
        if "updated_at" in existing_columns:
            batch_op.drop_column("updated_at")
        if "created_at" in existing_columns:
            batch_op.drop_column("created_at")
