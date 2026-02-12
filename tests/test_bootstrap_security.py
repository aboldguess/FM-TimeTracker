"""Mini-README: Security regression tests for bootstrap onboarding and password secrecy."""

from unittest.mock import Mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.bootstrap_admin import reset_bootstrap_admin_password
from app.config import settings
from app.database import Base
from app.main import bootstrap_context, startup, templates
from app.models import Role, User
from app.security import verify_password


def _mock_bootstrap_session(admin_count: int, bootstrap_admins: int) -> Mock:
    """Build a SQLAlchemy-session-like mock for bootstrap context tests."""
    session = Mock()
    session.scalar.side_effect = [admin_count, bootstrap_admins]
    return session


def test_templates_never_render_bootstrap_password() -> None:
    """Ensure template rendering never leaks BOOTSTRAP_ADMIN_PASSWORD content."""
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    context = {
        "request": request,
        "show_bootstrap": True,
        "bootstrap_setup_required": True,
        "bootstrap_email": settings.bootstrap_admin_email,
        "bootstrap_onboarding_hint": "Set BOOTSTRAP_ADMIN_PASSWORD before first startup.",
        "bootstrap_password": settings.bootstrap_admin_password,
        "error": None,
    }

    landing = templates.get_template("landing.html").render(context)
    login = templates.get_template("login.html").render(context)

    assert settings.bootstrap_admin_password not in landing
    assert settings.bootstrap_admin_password not in login


def test_bootstrap_context_hides_sensitive_onboarding_hint_in_production(monkeypatch) -> None:
    """Production should hide bootstrap email hints unless explicitly enabled."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secure_bootstrap_onboarding", False)

    context = bootstrap_context(_mock_bootstrap_session(admin_count=0, bootstrap_admins=0))

    assert context["bootstrap_setup_required"] is True
    assert context["show_bootstrap"] is False
    assert context["bootstrap_email"] is None
    assert "BOOTSTRAP_ADMIN_PASSWORD" in context["bootstrap_onboarding_hint"]


def test_bootstrap_context_allows_safe_hint_when_secure_onboarding_enabled(monkeypatch) -> None:
    """Secure onboarding override should enable non-sensitive setup guidance."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secure_bootstrap_onboarding", True)

    context = bootstrap_context(_mock_bootstrap_session(admin_count=0, bootstrap_admins=0))

    assert context["show_bootstrap"] is True
    assert context["bootstrap_email"] == settings.bootstrap_admin_email
    assert settings.bootstrap_admin_password not in context["bootstrap_onboarding_hint"]


def test_bootstrap_context_for_bootstrap_only_admin_guides_rotation(monkeypatch) -> None:
    """When only bootstrap admin exists, operators should be guided to rotate credentials."""
    monkeypatch.setattr(settings, "environment", "development")
    context = bootstrap_context(_mock_bootstrap_session(admin_count=1, bootstrap_admins=1))

    assert context["bootstrap_setup_required"] is True
    assert context["show_bootstrap"] is True
    assert "Bootstrap account exists" in context["bootstrap_onboarding_hint"]


def test_bootstrap_context_for_non_bootstrap_admin_suppresses_setup_message(monkeypatch) -> None:
    """Once a non-bootstrap admin exists, setup messaging should be suppressed."""
    monkeypatch.setattr(settings, "environment", "development")
    context = bootstrap_context(_mock_bootstrap_session(admin_count=2, bootstrap_admins=1))

    assert context["bootstrap_setup_required"] is False
    assert context["show_bootstrap"] is False
    assert context["bootstrap_onboarding_hint"] == ""


def test_startup_creates_hashed_bootstrap_admin(monkeypatch, tmp_path) -> None:
    """Startup should hash BOOTSTRAP_ADMIN_PASSWORD instead of storing plaintext."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'startup_bootstrap.db'}", future=True)
    Base.metadata.create_all(test_engine)

    monkeypatch.setattr("app.main.engine", test_engine)
    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr(settings, "bootstrap_admin_email", "bootstrap@example.com")
    monkeypatch.setattr(settings, "bootstrap_admin_password", "HighlySensitivePass!456")

    startup()

    with Session(test_engine) as db:
        admin = db.scalar(select(User).where(User.role == Role.ADMIN))

    assert admin is not None
    assert admin.email == settings.bootstrap_admin_email
    assert admin.hashed_password != settings.bootstrap_admin_password
    assert settings.bootstrap_admin_password not in admin.hashed_password


def test_startup_does_not_overwrite_existing_admin_password(monkeypatch, tmp_path, caplog) -> None:
    """Startup should not rotate existing admin passwords from environment values."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'startup_existing_admin.db'}", future=True)
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as db:
        db.add(
            User(
                email="existing-admin@example.com",
                full_name="Existing Admin",
                hashed_password="existing-hash-placeholder",
                role=Role.ADMIN,
                cost_rate=120,
                bill_rate=250,
            )
        )
        db.commit()

    monkeypatch.setattr("app.main.engine", test_engine)
    monkeypatch.setattr("app.main.run_migrations", lambda: None)
    monkeypatch.setattr(settings, "bootstrap_admin_email", "bootstrap@example.com")
    monkeypatch.setattr(settings, "bootstrap_admin_password", "NewBootstrapPass!123")

    caplog.set_level("INFO")
    startup()

    with Session(test_engine) as db:
        existing_admin = db.scalar(select(User).where(User.email == "existing-admin@example.com"))
        bootstrap_admin = db.scalar(select(User).where(User.email == "bootstrap@example.com"))

    assert existing_admin is not None
    assert existing_admin.hashed_password == "existing-hash-placeholder"
    assert bootstrap_admin is None
    assert "ignored after initial bootstrap" in caplog.text


def test_reset_bootstrap_admin_password_updates_hash_and_forces_rotation(tmp_path) -> None:
    """Password reset utility should hash new value and force change on next login."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'bootstrap_reset.db'}", future=True)
    Base.metadata.create_all(test_engine)
    original_password = "OriginalStrongPass!123"
    updated_password = "UpdatedStrongPass!456"

    with Session(test_engine) as db:
        db.add(
            User(
                email="bootstrap@example.com",
                full_name="Bootstrap Admin",
                hashed_password=original_password,
                role=Role.ADMIN,
                cost_rate=120,
                bill_rate=250,
                must_change_password=False,
            )
        )
        db.commit()

    updated = reset_bootstrap_admin_password(
        engine=test_engine,
        new_password=updated_password,
        bootstrap_email="bootstrap@example.com",
    )

    with Session(test_engine) as db:
        admin = db.scalar(select(User).where(User.email == "bootstrap@example.com"))

    assert updated is True
    assert admin is not None
    assert admin.hashed_password != updated_password
    assert verify_password(updated_password, admin.hashed_password)
    assert admin.must_change_password is True


def test_reset_bootstrap_admin_password_returns_false_when_user_missing(tmp_path) -> None:
    """Utility should fail safely when bootstrap admin does not exist."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'bootstrap_reset_missing.db'}", future=True)
    Base.metadata.create_all(test_engine)

    updated = reset_bootstrap_admin_password(
        engine=test_engine,
        new_password="AnyStrongPass!123",
        bootstrap_email="missing@example.com",
    )

    assert updated is False
