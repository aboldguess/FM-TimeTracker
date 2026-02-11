"""Mini-README: CSRF protection helpers.

This module provides a signed double-submit CSRF implementation for the
FastAPI app. It issues per-session tokens, validates submitted tokens on
mutating requests, and exposes helpers that can be reused by middleware,
dependencies, and templates.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Request

from app.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
_MUTATING_METHODS = {"POST", "PATCH", "DELETE"}


def _session_binding(request: Request) -> str:
    """Bind CSRF signatures to the authenticated session token when present."""
    return request.cookies.get("session_token") or "anonymous-session"


def _sign_nonce(nonce: str, session_binding: str) -> str:
    """Return HMAC signature for the nonce and session binding."""
    payload = f"{nonce}:{session_binding}".encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _is_token_well_formed(token: str | None) -> bool:
    return bool(token and "." in token)


def _build_token(request: Request) -> str:
    """Generate a fresh signed CSRF token."""
    nonce = secrets.token_urlsafe(32)
    signature = _sign_nonce(nonce, _session_binding(request))
    return f"{nonce}.{signature}"


def is_csrf_token_valid(request: Request, token: str | None) -> bool:
    """Validate signed double-submit token against cookie and session binding."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token or not cookie_token:
        return False
    if not hmac.compare_digest(token, cookie_token):
        return False
    if not _is_token_well_formed(token):
        return False

    nonce, signature = token.rsplit(".", 1)
    expected = _sign_nonce(nonce, _session_binding(request))
    return hmac.compare_digest(signature, expected)


def get_or_create_csrf_token(request: Request) -> str:
    """Return current request token or create a new token when missing/invalid."""
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    if existing and is_csrf_token_valid(request, existing):
        return existing
    return _build_token(request)


def should_enforce_csrf(request: Request) -> bool:
    """Return True when CSRF checks should run for this request."""
    if request.method.upper() not in _MUTATING_METHODS:
        return False
    path = request.url.path
    if path.startswith("/static"):
        return False
    return True


def is_same_origin(request: Request) -> bool:
    """Allow requests with no Origin and block explicit cross-site Origins."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    origin_parts = urlsplit(origin)
    request_parts = urlsplit(str(request.url))
    return (
        origin_parts.scheme.lower(),
        origin_parts.netloc.lower(),
    ) == (
        request_parts.scheme.lower(),
        request_parts.netloc.lower(),
    )
