"""Mini-README: Regression tests for login parsing and guest splash layout behavior."""

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


def test_landing_page_uses_full_width_splash_layout_for_guests() -> None:
    """Guest users should get the full-width splash layout instead of sidebar-constrained content."""
    response = client.get("/")

    assert response.status_code == 200
    assert "app-shell--guest" in response.text
    assert "splash-hero" in response.text
