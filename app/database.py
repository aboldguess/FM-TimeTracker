"""Database module.

Provides SQLAlchemy engine/session setup and migration bootstrap helpers so
schema changes are explicit, reproducible, and safe across environments.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# First Alembic revision that captures the existing pre-migration schema.
BASELINE_REVISION = "17ed833d2e37"


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


def _has_existing_app_schema(db_engine: Engine) -> bool:
    """Return True when pre-existing app tables are present in the database."""
    inspector = inspect(db_engine)
    existing_tables = set(inspector.get_table_names())
    # Keep this list small and stable; these tables have existed across app versions.
    sentinel_tables = {"users", "timesheet_entries", "projects"}
    return any(table in existing_tables for table in sentinel_tables)


def _has_alembic_version(db_engine: Engine) -> bool:
    """Return True when Alembic has already tracked this database."""
    inspector = inspect(db_engine)
    if "alembic_version" not in inspector.get_table_names():
        return False
    with db_engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT version_num FROM alembic_version LIMIT 1").first()
    return row is not None and bool(row[0])


def _bootstrap_legacy_schema_if_required(alembic_cfg: Config, db_engine: Engine) -> None:
    """Stamp legacy pre-Alembic databases to baseline before upgrade.

    Without this, old environments with existing tables but no `alembic_version`
    would try to execute baseline CREATE TABLE DDL and fail at startup.
    """
    if _has_alembic_version(db_engine):
        return
    if not _has_existing_app_schema(db_engine):
        return

    logger.warning(
        "Detected legacy schema without alembic_version; stamping revision %s before upgrade.",
        BASELINE_REVISION,
    )
    command.stamp(alembic_cfg, BASELINE_REVISION)


def run_migrations() -> None:
    """Apply migrations, auto-bootstrapping legacy non-Alembic databases."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    _bootstrap_legacy_schema_if_required(alembic_cfg, engine)
    command.upgrade(alembic_cfg, "head")
    ensure_sqlite_schema(engine)
    logger.info("Database migrations applied successfully")


def ensure_sqlite_schema(db_engine: Engine) -> None:
    """Backfill missing SQLite columns for legacy local development databases.

    This is a development-only safety net for older non-migrated SQLite files.
    Alembic migrations remain the primary and authoritative schema mechanism.
    """
    if db_engine.dialect.name != "sqlite":
        return

    inspector = inspect(db_engine)
    table_names = set(inspector.get_table_names())

    # NOTE: keep this list intentionally additive-only and SQLite-compatible.
    # SQLite supports adding nullable columns safely with ALTER TABLE, which is
    # enough for our local legacy-db recovery path.
    sqlite_legacy_alter_statements: dict[str, list[tuple[str, str]]] = {
        "timesheet_entries": [
            (
                "created_at",
                "ALTER TABLE timesheet_entries "
                "ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
            ),
            ("updated_at", "ALTER TABLE timesheet_entries ADD COLUMN updated_at DATETIME"),
        ],
        "projects": [
            ("customer_id", "ALTER TABLE projects ADD COLUMN customer_id INTEGER"),
            ("programme_id", "ALTER TABLE projects ADD COLUMN programme_id INTEGER"),
        ],
    }

    with db_engine.begin() as connection:
        for table_name, statements in sqlite_legacy_alter_statements.items():
            if table_name not in table_names:
                logger.debug("SQLite schema check skipped: table '%s' not found.", table_name)
                continue

            column_names = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, statement in statements:
                if column_name in column_names:
                    continue
                logger.warning(
                    "Applying SQLite dev schema safety net: adding column '%s.%s'.",
                    table_name,
                    column_name,
                )
                connection.exec_driver_sql(statement)
                logger.info("Applied SQLite schema change: table=%s column=%s", table_name, column_name)
