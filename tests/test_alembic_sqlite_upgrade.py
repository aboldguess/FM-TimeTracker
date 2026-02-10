"""Mini-README: Regression tests for SQLite-safe behavior in password migration revision."""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from pathlib import Path


def _load_revision_module():
    """Load the Alembic revision module directly from file path."""
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "9f7a1c2b4d5e_add_must_change_password_to_users.py"
    )
    spec = importlib.util.spec_from_file_location("revision_9f7a1c2b4d5e", revision_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_password_migration_skips_alter_column_on_sqlite(monkeypatch) -> None:
    """SQLite should add the column but skip dropping the default via alter_column."""
    revision = _load_revision_module()

    calls = {"add": 0, "alter": 0}

    class FakeOp:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def add_column(self, *_args, **_kwargs):
            calls["add"] += 1

        def alter_column(self, *_args, **_kwargs):
            calls["alter"] += 1

    class FakeInspector:
        @staticmethod
        def get_columns(_table_name: str):
            return []

    monkeypatch.setattr(revision, "op", FakeOp())
    monkeypatch.setattr(revision, "inspect", lambda _bind: FakeInspector())

    revision.upgrade()

    assert calls["add"] == 1
    assert calls["alter"] == 0


def test_password_migration_keeps_alter_column_for_non_sqlite(monkeypatch) -> None:
    """Non-SQLite dialects should continue removing the server default after add."""
    revision = _load_revision_module()

    calls = {"add": 0, "alter": 0}

    class FakeOp:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def add_column(self, *_args, **_kwargs):
            calls["add"] += 1

        def alter_column(self, *_args, **_kwargs):
            calls["alter"] += 1

    class FakeInspector:
        @staticmethod
        def get_columns(_table_name: str):
            return []

    monkeypatch.setattr(revision, "op", FakeOp())
    monkeypatch.setattr(revision, "inspect", lambda _bind: FakeInspector())

    revision.upgrade()

    assert calls["add"] == 1
    assert calls["alter"] == 1
