"""Database module.

Provides SQLAlchemy engine/session setup and dependency helpers. The app is
configured to use SQLite by default for easy local testing but accepts any
SQLAlchemy-compatible DB URL for deployment.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base declarative class for all ORM entities."""


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency that yields a transaction-capable DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
