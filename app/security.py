"""Security helpers.

Contains password hashing/verification and signed session-token utilities.
Designed for secure defaults and easy upgrades.
"""

from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(settings.secret_key, salt="fm-timetracker-session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
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
