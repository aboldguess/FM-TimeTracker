"""Mini-README: Regression tests for login parsing and guest splash layout behavior."""

import logging

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


client = TestClient(app)


def setup_module() -> None:
    """Ensure schema exists for login-flow template routes in isolated test runs."""
    Base.metadata.create_all(engine)


def _csrf_token() -> str:
    """Fetch a CSRF token from the login page cookie jar."""
    response = client.get("/login")
    assert response.status_code == 200
    token = client.cookies.get("csrf_token")
    assert token
    return token


def test_login_json_payload_missing_fields_returns_validation_page_not_422() -> None:
    """JSON login requests should render the same friendly validation messaging as form posts."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json={},
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Enter a valid email address" in response.text
    assert "Field required" not in response.text


def test_login_invalid_email_returns_email_specific_message() -> None:
    """Malformed email should return the dedicated email validation hint."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json={"email": "not-an-email", "password": "any-password"},
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Enter a valid email address" in response.text


def test_login_missing_password_returns_password_specific_message() -> None:
    """Missing password should return a password-specific validation message."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json={"email": "admin@change.me"},
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Enter your password to continue." in response.text


def test_login_non_dict_json_returns_generic_format_message() -> None:
    """Unexpected JSON shape should return a generic request-format error."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json=["unexpected", "shape"],
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Invalid login request format." in response.text


def test_login_form_trims_whitespace_before_email_validation() -> None:
    """Whitespace around email should not trigger malformed-email validation errors."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json={
            "email": "  admin@change.me  ",
            "password": "wrong-password",
        },
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 401
    assert "Enter a valid email address" not in response.text
    assert "Invalid credentials" in response.text


def test_login_form_normalizes_unicode_compatibility_email_before_validation() -> None:
    """Full-width compatibility variants should normalize to a valid email string."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json={
            "email": "ａｄｍｉｎ＠ｃｈａｎｇｅ.ｍｅ",
            "password": "wrong-password",
        },
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 401
    assert "Enter a valid email address" not in response.text
    assert "Invalid credentials" in response.text


def test_login_form_removes_zero_width_chars_before_email_validation() -> None:
    """Zero-width Unicode characters in email input should be stripped pre-validation."""
    token = _csrf_token()
    response = client.post(
        "/login",
        json={
            "email": "ad\u200bmin@cha\u200cnge.me",
            "password": "wrong-password",
        },
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 401
    assert "Enter a valid email address" not in response.text
    assert "Invalid credentials" in response.text


def test_login_rejects_zero_width_space_contaminated_visual_lookalike_email(caplog) -> None:
    """Visually similar emails altered with zero-width characters should be rejected with safe feedback."""
    caplog.set_level(logging.INFO, logger="auth.login")
    token = _csrf_token()
    response = client.post(
        "/login",
        json={
            "email": "admin@change\u200bme",
            "password": "wrong-password",
        },
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Enter a valid email address" in response.text
    assert "admin@change\u200bme" not in response.text
    assert "Traceback" not in response.text
    assert "login_validation_failed" in caplog.text
    assert "email_key_present=True" in caplog.text
    assert "password_key_present=True" in caplog.text
    assert "login_validation_error_item loc=('email',)" in caplog.text


def test_login_missing_email_key_logs_actionable_diagnostics(caplog) -> None:
    """Requests with a wrong email key should return safe UI feedback and precise diagnostics."""
    caplog.set_level(logging.INFO, logger="auth.login")
    token = _csrf_token()
    response = client.post(
        "/login",
        json={
            "username": "admin@change.me",
            "password": "wrong-password",
        },
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Enter a valid email address" in response.text
    assert "Field required" not in response.text
    assert "login_validation_failed" in caplog.text
    assert "source=json" in caplog.text
    assert "email_key_present=False" in caplog.text
    assert "password_key_present=True" in caplog.text
    assert "login_validation_error_item loc=('email',)" in caplog.text


def test_login_rejects_email_with_control_characters_and_logs_context(caplog) -> None:
    """Control-character contaminated email should fail safely and be logged for debugging."""
    caplog.set_level(logging.INFO, logger="auth.login")
    token = _csrf_token()
    response = client.post(
        "/login",
        json={
            "email": "admin@change\u0000me",
            "password": "wrong-password",
        },
        headers={"x-csrf-token": token},
    )

    assert response.status_code == 400
    assert "Enter a valid email address" in response.text
    assert "Invalid login request format." not in response.text
    assert "login_validation_failed" in caplog.text
    assert "email_key_present=True" in caplog.text
    assert "password_key_present=True" in caplog.text
    assert "email_repr='admin@changeme'" in caplog.text
    assert "login_validation_error_item loc=('email',)" in caplog.text


def test_landing_page_uses_full_width_splash_layout_for_guests() -> None:
    """Guest users should get the full-width splash layout instead of sidebar-constrained content."""
    response = client.get("/")

    assert response.status_code == 200
    assert "app-shell--guest" in response.text
    assert "splash-hero" in response.text
