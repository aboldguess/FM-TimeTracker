"""Mini-README: CSRF regression tests for mutating FastAPI routes.

These tests prove that mutating endpoints reject missing CSRF tokens and
explicit cross-site attempts with HTTP 403 responses.
"""

import re

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


def _extract_csrf_token(html: str) -> str:
    """Read the CSRF hidden input from an HTML page."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_mutating_route_rejects_missing_csrf_token() -> None:
    """Form submissions without a CSRF token must be blocked."""
    Base.metadata.create_all(engine)
    client = TestClient(app)

    response = client.post("/company/defaults", data={"default_hours_mon": "8"})

    assert response.status_code == 403
    assert "CSRF" in response.text


def test_mutating_route_rejects_cross_site_origin_even_with_token() -> None:
    """Cross-site mutating requests should fail same-origin checks."""
    Base.metadata.create_all(engine)
    client = TestClient(app)

    login_page = client.get("/login")
    csrf_token = _extract_csrf_token(login_page.text)

    response = client.post(
        "/login",
        data={
            "email": "attacker@example.com",
            "password": "WrongPassword!123",
            "csrf_token": csrf_token,
        },
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert "origin" in response.text.lower()
