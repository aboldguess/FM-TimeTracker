"""Mini-README: Bootstrap admin operational helpers.

This module contains narrowly scoped helpers for bootstrap-account lifecycle
operations that are safer to test and reuse than ad-hoc SQL in shell snippets.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Role, User
from app.security import hash_password


def reset_bootstrap_admin_password(*, engine, new_password: str, bootstrap_email: str | None = None) -> bool:
    """Reset the configured bootstrap admin password using secure hashing.

    Returns True when the target bootstrap admin user is found and updated,
    otherwise False.
    """
    target_email = (bootstrap_email or settings.bootstrap_admin_email).strip().lower()
    with Session(engine) as db:
        bootstrap_admin = db.scalar(
            select(User).where(
                User.role == Role.ADMIN,
                func.lower(User.email) == target_email,
            )
        )
        if not bootstrap_admin:
            return False

        bootstrap_admin.hashed_password = hash_password(new_password)
        bootstrap_admin.must_change_password = True
        db.commit()

    return True
