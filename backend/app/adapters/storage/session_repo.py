from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import AuthSession


def create(
    session: Session,
    *,
    user_id: UUID,
    expires_at: datetime,
    user_agent: str | None,
) -> AuthSession:
    row = AuthSession(user_id=user_id, expires_at=expires_at, user_agent=user_agent)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_active(session: Session, session_id: UUID) -> AuthSession | None:
    stmt = select(AuthSession).where(
        AuthSession.id == session_id,
        AuthSession.expires_at > datetime.now(UTC),
    )
    return session.execute(stmt).scalar_one_or_none()


def delete(session: Session, session_id: UUID) -> None:
    stmt = sa_delete(AuthSession).where(AuthSession.id == session_id)
    session.execute(stmt)
    session.commit()


def touch_last_seen(session: Session, session_id: UUID) -> None:
    stmt = (
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(last_seen_at=datetime.now(UTC))
    )
    session.execute(stmt)
    session.commit()
