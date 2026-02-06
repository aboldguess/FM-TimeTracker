"""Security helpers.

Contains password hashing/verification and signed session-token utilities.
Designed for secure defaults and easy upgrades.
"""

from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from passlib.exc import MissingBackendError

from app.config import settings

# Argon2 is memory-hard and resilient against GPU/ASIC cracking.
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)
# Signed serializer protects session payload integrity.
serializer = URLSafeSerializer(settings.secret_key, salt="fm-timetracker-session")


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2."""
    return pwd_context.hash(password)


def ensure_password_backend() -> None:
    """Validate Argon2 backend availability with a lightweight hash."""
    try:
        # This keeps the check fast while still proving the backend is usable.
        pwd_context.hash("argon2-backend-check")
    except MissingBackendError as exc:
        raise RuntimeError(
            "Argon2 backend unavailable. Install argon2-cffi in the active virtual environment."
        ) from exc


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return pwd_context.verify(password, hashed_password)


def create_session_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "exp": (datetime.now(timezone.utc) + timedelta(hours=12)).timestamp(),
    }
    return serializer.dumps(payload)


def read_session_token(token: str) -> int | None:
    try:
        payload = serializer.loads(token)
    except BadSignature:
        return None
    if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
        return None
    return payload.get("sub")
