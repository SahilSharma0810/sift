"""SQLAlchemy session factory.

Sync engine + sessionmaker, per ADR-0002. Use `get_session()` as a FastAPI
dependency in route handlers (via services).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI-friendly session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
