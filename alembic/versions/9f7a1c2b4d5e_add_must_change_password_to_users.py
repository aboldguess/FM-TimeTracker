"""Add must_change_password flag to users.

Revision ID: 9f7a1c2b4d5e
Revises: 64b8f8ccdf7c
Create Date: 2026-02-10 14:20:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "9f7a1c2b4d5e"
down_revision: str | None = "64b8f8ccdf7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    if "must_change_password" not in existing_columns:
        op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.alter_column("users", "must_change_password", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    if "must_change_password" in existing_columns:
        op.drop_column("users", "must_change_password")
