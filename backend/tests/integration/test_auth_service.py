from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.session_repo import get_active as get_active_session
from app.adapters.storage.user_repo import upsert_demo_user
from app.config import get_settings
from app.services.auth_service import LoginOutcome, login


SECRET = "test-secret-do-not-use-in-prod"
SETTINGS = get_settings()


class TestLogin:
    def _seed_user(self, db_session: Session):
        return upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="correct-password",
        )

    def test_success_returns_outcome_and_creates_session(
        self, db_session: Session
    ) -> None:
        user = self._seed_user(db_session)
        outcome = login(
            db_session,
            email="ap-clerk@example.test",
            password="correct-password",
            remember=False,
            user_agent="pytest",
            secret=SECRET,
        )
        assert isinstance(outcome, LoginOutcome)
        assert outcome.clerk.id == user.id
        assert outcome.clerk.email.lower() == "ap-clerk@example.test"
        assert outcome.signed_cookie
        assert outcome.max_age_seconds == SETTINGS.session_default_hours * 3600

    def test_remember_flag_extends_max_age(self, db_session: Session) -> None:
        self._seed_user(db_session)
        outcome = login(
            db_session,
            email="ap-clerk@example.test",
            password="correct-password",
            remember=True,
            user_agent=None,
            secret=SECRET,
        )
        assert outcome is not None
        assert outcome.max_age_seconds == SETTINGS.session_remember_days * 86400

    def test_wrong_password_returns_none_and_does_not_create_session(
        self, db_session: Session
    ) -> None:
        user = self._seed_user(db_session)
        outcome = login(
            db_session,
            email="ap-clerk@example.test",
            password="wrong",
            remember=False,
            user_agent=None,
            secret=SECRET,
        )
        assert outcome is None
        from sqlalchemy import select
        from app.db.models import AuthSession

        rows = db_session.execute(
            select(AuthSession).where(AuthSession.user_id == user.id)
        ).all()
        assert rows == []

    def test_unknown_email_returns_none(self, db_session: Session) -> None:
        outcome = login(
            db_session,
            email="nobody@example.test",
            password="anything",
            remember=False,
            user_agent=None,
            secret=SECRET,
        )
        assert outcome is None

    def test_login_updates_last_login_at(self, db_session: Session) -> None:
        user = self._seed_user(db_session)
        assert user.last_login_at is None
        login(
            db_session,
            email="ap-clerk@example.test",
            password="correct-password",
            remember=False,
            user_agent=None,
            secret=SECRET,
        )
        db_session.refresh(user)
        assert user.last_login_at is not None

    def test_unknown_email_takes_real_time(self, db_session: Session) -> None:
        start = time.perf_counter()
        login(
            db_session,
            email="nobody@example.test",
            password="x",
            remember=False,
            user_agent=None,
            secret=SECRET,
        )
        elapsed = time.perf_counter() - start
        assert elapsed > 0.001


class TestResolveSession:
    def _login(self, db_session: Session, *, remember: bool = False):
        upsert_demo_user(db_session, email="resolve@example.test", password="pw")
        return login(
            db_session,
            email="resolve@example.test",
            password="pw",
            remember=remember,
            user_agent="pytest",
            secret=SECRET,
        )

    def test_resolves_valid_cookie(self, db_session: Session) -> None:
        from app.services.auth_service import resolve_session

        outcome = self._login(db_session)
        assert outcome is not None
        clerk = resolve_session(db_session, outcome.signed_cookie, secret=SECRET)
        assert clerk is not None
        assert clerk.email.lower() == "resolve@example.test"

    def test_returns_none_for_none_or_empty(self, db_session: Session) -> None:
        from app.services.auth_service import resolve_session

        assert resolve_session(db_session, None, secret=SECRET) is None
        assert resolve_session(db_session, "", secret=SECRET) is None

    def test_returns_none_for_tampered_cookie(self, db_session: Session) -> None:
        from app.services.auth_service import resolve_session

        outcome = self._login(db_session)
        assert outcome is not None
        tampered = outcome.signed_cookie + "x"
        assert resolve_session(db_session, tampered, secret=SECRET) is None

    def test_returns_none_when_wrong_secret(self, db_session: Session) -> None:
        from app.services.auth_service import resolve_session

        outcome = self._login(db_session)
        assert outcome is not None
        assert resolve_session(db_session, outcome.signed_cookie, secret="other") is None

    def test_returns_none_and_deletes_row_when_session_expired(
        self, db_session: Session
    ) -> None:
        from app.services.auth_service import resolve_session
        from sqlalchemy import update
        from app.db.models import AuthSession

        outcome = self._login(db_session)
        assert outcome is not None

        db_session.execute(
            update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db_session.commit()

        assert resolve_session(db_session, outcome.signed_cookie, secret=SECRET) is None
        from sqlalchemy import select

        remaining = db_session.execute(select(AuthSession)).all()
        assert remaining == []

    def test_touches_last_seen_on_resolve(self, db_session: Session) -> None:
        from app.services.auth_service import resolve_session
        from sqlalchemy import select
        from app.db.models import AuthSession

        outcome = self._login(db_session)
        assert outcome is not None
        before_row = db_session.execute(select(AuthSession)).scalar_one()
        before = before_row.last_seen_at

        time.sleep(0.01)
        resolve_session(db_session, outcome.signed_cookie, secret=SECRET)
        db_session.refresh(before_row)
        assert before_row.last_seen_at > before
