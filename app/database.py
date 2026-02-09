"""Database module.

Provides SQLAlchemy engine/session setup, schema helpers, and dependency
utilities. The app is configured to use SQLite by default for easy local
testing but accepts any SQLAlchemy-compatible DB URL for deployment.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all ORM entities."""


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency that yields a transaction-capable DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_schema() -> None:
    """Apply lightweight SQLite schema fixes for legacy databases.

    SQLite doesn't support ALTER TABLE ... ADD CONSTRAINT in-place, so we only
    add missing columns with sane defaults and log any change for debugging.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    column_fixes = [
        ("manager_id", "INTEGER"),
        ("working_hours_mon", "REAL NOT NULL DEFAULT 8"),
        ("working_hours_tue", "REAL NOT NULL DEFAULT 8"),
        ("working_hours_wed", "REAL NOT NULL DEFAULT 8"),
        ("working_hours_thu", "REAL NOT NULL DEFAULT 8"),
        ("working_hours_fri", "REAL NOT NULL DEFAULT 8"),
        ("working_hours_sat", "REAL NOT NULL DEFAULT 0"),
        ("working_hours_sun", "REAL NOT NULL DEFAULT 0"),
    ]
    with engine.begin() as connection:
        for column_name, ddl in column_fixes:
            if column_name in existing_columns:
                continue
            logger.info("Applying SQLite schema fix: users.%s", column_name)
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {ddl}"))
            existing_columns.add(column_name)
