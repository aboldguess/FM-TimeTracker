"""Mini-README: Security regression tests for bootstrap onboarding and password secrecy."""

from unittest.mock import Mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import settings
from app.database import Base
from app.main import bootstrap_context, startup, templates
from app.models import Role, User


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
