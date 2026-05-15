from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.adapters.storage import session_repo, user_repo
from app.config import get_settings
from app.domain.auth import (
    DUMMY_PASSWORD_HASH,
    ClerkOut,
    sign_session_id,
    unsign_session_id,
    verify_password,
)


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    clerk: ClerkOut
    signed_cookie: str
    max_age_seconds: int | None


def _to_clerk(user) -> ClerkOut:
    return ClerkOut(id=user.id, email=str(user.email), display_name=user.display_name)


def login(
    session: Session,
    *,
    email: str,
    password: str,
    remember: bool,
    user_agent: str | None,
    secret: str | None = None,
) -> LoginOutcome | None:
    settings = get_settings()
    secret_key = secret or settings.secret_key

    user = user_repo.get_by_email(session, email)
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, user.password_hash):
        return None

    if remember:
        max_age_seconds = settings.session_remember_days * 86400
    else:
        max_age_seconds = settings.session_default_hours * 3600

    expires_at = datetime.now(UTC) + timedelta(seconds=max_age_seconds)
    auth_session = session_repo.create(
        session,
        user_id=user.id,
        expires_at=expires_at,
        user_agent=user_agent,
    )
    user_repo.update_last_login(session, user_id=user.id)

    return LoginOutcome(
        clerk=_to_clerk(user),
        signed_cookie=sign_session_id(auth_session.id, secret=secret_key),
        max_age_seconds=max_age_seconds,
    )


def resolve_session(
    session: Session,
    signed_cookie: str | None,
    *,
    secret: str | None = None,
) -> ClerkOut | None:
    if not signed_cookie:
        return None

    settings = get_settings()
    secret_key = secret or settings.secret_key

    session_id = unsign_session_id(signed_cookie, secret=secret_key)
    if session_id is None:
        return None

    auth_session = session_repo.get_active(session, session_id)
    if auth_session is None:
        session_repo.delete(session, session_id)
        return None

    user = auth_session.user
    if user is None:
        session_repo.delete(session, session_id)
        return None

    session_repo.touch_last_seen(session, session_id)
    return _to_clerk(user)


def logout(
    session: Session,
    signed_cookie: str | None,
    *,
    secret: str | None = None,
) -> None:
    if not signed_cookie:
        return

    settings = get_settings()
    secret_key = secret or settings.secret_key

    session_id = unsign_session_id(signed_cookie, secret=secret_key)
    if session_id is None:
        return

    session_repo.delete(session, session_id)
