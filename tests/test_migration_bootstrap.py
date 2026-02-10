"""Mini-README: Regression tests for Alembic bootstrap behavior on legacy DBs."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from app.database import (
    BASELINE_REVISION,
    _bootstrap_legacy_schema_if_required,
    _has_alembic_version,
    _has_existing_app_schema,
    ensure_sqlite_schema,
)


def _empty_alembic_config() -> Config:
    """Create a minimal Config object suitable for unit tests."""
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    return cfg


def test_detects_legacy_schema_without_alembic_tracking(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))

    assert _has_existing_app_schema(engine) is True
    assert _has_alembic_version(engine) is False

    stamped: list[str] = []

    def fake_stamp(_: Config, revision: str) -> None:
        stamped.append(revision)

    monkeypatch.setattr("app.database.command.stamp", fake_stamp)

    _bootstrap_legacy_schema_if_required(_empty_alembic_config(), engine)

    assert stamped == [BASELINE_REVISION]


def test_does_not_stamp_fresh_database(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    stamped: list[str] = []

    def fake_stamp(_: Config, revision: str) -> None:
        stamped.append(revision)

    monkeypatch.setattr("app.database.command.stamp", fake_stamp)

    _bootstrap_legacy_schema_if_required(_empty_alembic_config(), engine)

    assert _has_existing_app_schema(engine) is False
    assert stamped == []


def test_does_not_stamp_when_alembic_version_exists(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('64b8f8ccdf7c')"))

    stamped: list[str] = []

    def fake_stamp(_: Config, revision: str) -> None:
        stamped.append(revision)

    monkeypatch.setattr("app.database.command.stamp", fake_stamp)

    _bootstrap_legacy_schema_if_required(_empty_alembic_config(), engine)

    assert _has_alembic_version(engine) is True
    assert stamped == []


def test_sqlite_safety_net_backfills_missing_projects_columns() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE projects "
                "(id INTEGER PRIMARY KEY, name VARCHAR(140) NOT NULL, description TEXT NOT NULL)"
            )
        )

    ensure_sqlite_schema(engine)

    with engine.begin() as connection:
        columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(projects)")).fetchall()
        }

    assert "customer_id" in columns
    assert "programme_id" in columns
