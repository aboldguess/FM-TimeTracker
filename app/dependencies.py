"""Dependency helpers.

Provides authentication and role-gating dependencies for FastAPI routes.
"""

from collections.abc import Iterable

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User
from app.security import read_session_token


def get_current_user(session_token: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = read_session_token(session_token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


def require_roles(*roles: Role):
    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return _checker


def can_manage_target(actor: User, target_role: Role) -> bool:
    matrix: dict[Role, Iterable[Role]] = {
        Role.ADMIN: [Role.ADMIN, Role.PROGRAMME_MANAGER, Role.PROJECT_MANAGER, Role.STAFF],
        Role.PROGRAMME_MANAGER: [Role.PROJECT_MANAGER, Role.STAFF],
        Role.PROJECT_MANAGER: [Role.STAFF],
        Role.STAFF: [],
    }
    return target_role in matrix[actor.role]
