from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import User
from app.domain.auth import hash_password


def get_by_email(session: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return session.execute(stmt).scalar_one_or_none()


def update_last_login(session: Session, *, user_id: UUID) -> None:
    stmt = update(User).where(User.id == user_id).values(last_login_at=datetime.now(UTC))
    session.execute(stmt)
    session.commit()


def upsert_demo_user(session: Session, *, email: str, password: str) -> User:
    existing = get_by_email(session, email)
    if existing is not None:
        return existing
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
