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
