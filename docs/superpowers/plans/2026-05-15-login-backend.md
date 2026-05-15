# Login Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `LoginScreen.tsx` UI to a real backend with single-clerk auth: argon2-hashed passwords, server-side `auth_sessions` rows, HttpOnly signed cookie, and a `get_current_clerk` dependency gating the existing protected routes.

**Architecture:** Four-layer per [ADR-0005](../../adr/0005-layered-architecture.md). `domain/auth.py` holds pure crypto and Pydantic DTOs. `services/auth_service.py` orchestrates login/logout/resolve. `adapters/storage/user_repo.py` + `session_repo.py` own DB IO. `api/auth.py` exposes endpoints; `api/deps.py` provides the route guard. One Alembic revision adds `users` + `auth_sessions` (+ `citext`). Frontend wires the login form, adds a boot guard in `Shell`, and a sign-out control.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (sync) + Postgres (`citext`) + Alembic + Pydantic v2 + `argon2-cffi` + `itsdangerous` + structlog. Frontend: React + Vite + TypeScript + TanStack Query + Tailwind.

**Source spec:** [docs/superpowers/specs/2026-05-15-login-backend-design.md](../specs/2026-05-15-login-backend-design.md). When this plan and the spec disagree, the spec wins; raise the discrepancy.

**Style:** Match the spec's "Code style — comments" section. Default to no comments. Add one only when *why* is non-obvious. Don't narrate *what*. Reference no task/ADR/caller in inline comments — those belong in commit messages.

---

## File Structure

**New files:**
- `backend/app/domain/auth.py` — `ClerkOut`, `LoginIn`; `hash_password`, `verify_password`; `sign_session_id`, `unsign_session_id`; `DUMMY_PASSWORD_HASH` constant.
- `backend/app/adapters/storage/user_repo.py` — `get_by_email`, `update_last_login`, `upsert_demo_user`.
- `backend/app/adapters/storage/session_repo.py` — `create`, `get_active`, `delete`, `touch_last_seen`.
- `backend/app/services/auth_service.py` — `LoginOutcome` dataclass, `login`, `resolve_session`, `logout`.
- `backend/app/api/auth.py` — `POST /login`, `POST /logout`, `GET /me`.
- `backend/app/api/deps.py` — `get_current_clerk` FastAPI dependency.
- `backend/alembic/versions/<new>_add_users_and_auth_sessions.py` — migration.
- `backend/tests/unit/test_auth_domain.py` — unit tests for `domain/auth.py`.
- `backend/tests/integration/test_auth_repos.py` — repo tests against real Postgres.
- `backend/tests/integration/test_auth_service.py` — service-layer tests.
- `backend/tests/integration/test_auth_api.py` — endpoint tests.
- `frontend/src/state/auth.ts` — `useMeQuery`, `useLoginMutation`, `useLogoutMutation`.

**Modified files:**
- `backend/app/db/models.py` — add `User`, `AuthSession` ORM classes.
- `backend/app/config.py` — add `secret_key`, `cookie_secure`, `session_remember_days`, `session_default_hours`, `demo_email`, `demo_password`.
- `backend/app/main.py` — register `app.api.auth` router.
- `backend/app/api/invoices.py` — add `Depends(get_current_clerk)` to every endpoint.
- `backend/app/api/search.py` — add `Depends(get_current_clerk)` to every endpoint.
- `backend/app/domain/models.py` — re-export `ClerkOut`, `LoginIn` so `scripts/generate_types.py` picks them up.
- `backend/pyproject.toml` — add `argon2-cffi`, `itsdangerous`.
- `backend/scripts/seed_demo.py` — call `seed_demo_user` at start of `main()`.
- `backend/tests/integration/conftest.py` — `api_client` becomes authed; new `unauthed_client` fixture.
- `.env.example` — new keys.
- `DEPLOY.md` — production secrets note.
- `frontend/src/state/api.ts` — always send credentials; pluggable 401 handler.
- `frontend/src/routes/LoginScreen.tsx` — wire submit to API; inline error state.
- `frontend/src/components/shell/Shell.tsx` — boot guard via `useMeQuery`; sign-out control.
- `frontend/src/types/generated/domain.ts` — regenerated.

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Edit `backend/pyproject.toml`** — add two entries inside the existing `dependencies = [...]` list (alphabetical zone, after `anthropic>=0.39.0`):

```toml
    "argon2-cffi>=23.1.0",
    "itsdangerous>=2.2.0",
```

- [ ] **Step 2: Rebuild the backend container so the new wheels install**

Run:
```bash
docker compose build backend
docker compose up -d backend
```

Expected: build succeeds; `docker compose exec backend uv pip list | grep -E 'argon2|itsdangerous'` shows both packages.

- [ ] **Step 3: Smoke import**

Run:
```bash
docker compose exec backend uv run python -c "import argon2, itsdangerous; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): add argon2-cffi and itsdangerous for auth"
```

---

## Task 2: Password hashing in `domain/auth.py`

**Files:**
- Create: `backend/app/domain/auth.py`
- Test: `backend/tests/unit/test_auth_domain.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/unit/test_auth_domain.py`:

```python
from __future__ import annotations

import pytest

from app.domain.auth import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_roundtrip(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed) is True

    def test_hash_rejects_wrong_password(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("wrong-password", hashed) is False

    def test_dummy_hash_is_a_valid_argon2_hash(self) -> None:
        assert verify_password("anything", DUMMY_PASSWORD_HASH) is False

    def test_dummy_hash_takes_real_time_to_verify(self) -> None:
        import time

        start = time.perf_counter()
        verify_password("anything", DUMMY_PASSWORD_HASH)
        elapsed = time.perf_counter() - start
        assert elapsed > 0.001
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/unit/test_auth_domain.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.auth'`.

- [ ] **Step 3: Implement** — create `backend/app/domain/auth.py`:

```python
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_HASHER = PasswordHasher()

DUMMY_PASSWORD_HASH: str = _HASHER.hash("dummy-for-timing-only")


def hash_password(plaintext: str) -> str:
    return _HASHER.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _HASHER.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
    except Exception:
        return False
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/unit/test_auth_domain.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/auth.py backend/tests/unit/test_auth_domain.py
git commit -m "feat(auth): argon2 password hashing helpers"
```

---

## Task 3: Cookie signing in `domain/auth.py`

**Files:**
- Modify: `backend/app/domain/auth.py`
- Modify: `backend/tests/unit/test_auth_domain.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/unit/test_auth_domain.py`:

```python
import uuid


class TestCookieSigning:
    SECRET = "test-secret-do-not-use-in-prod"

    def test_sign_and_unsign_roundtrip(self) -> None:
        from app.domain.auth import sign_session_id, unsign_session_id

        sid = uuid.uuid4()
        signed = sign_session_id(sid, secret=self.SECRET)
        assert unsign_session_id(signed, secret=self.SECRET) == sid

    def test_unsign_rejects_tampered_value(self) -> None:
        from app.domain.auth import sign_session_id, unsign_session_id

        sid = uuid.uuid4()
        signed = sign_session_id(sid, secret=self.SECRET) + "x"
        assert unsign_session_id(signed, secret=self.SECRET) is None

    def test_unsign_rejects_wrong_secret(self) -> None:
        from app.domain.auth import sign_session_id, unsign_session_id

        sid = uuid.uuid4()
        signed = sign_session_id(sid, secret=self.SECRET)
        assert unsign_session_id(signed, secret="other-secret") is None

    def test_unsign_rejects_garbage(self) -> None:
        from app.domain.auth import unsign_session_id

        assert unsign_session_id("not-a-real-cookie", secret=self.SECRET) is None
        assert unsign_session_id("", secret=self.SECRET) is None
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/unit/test_auth_domain.py::TestCookieSigning -v
```

Expected: FAIL with `ImportError: cannot import name 'sign_session_id'`.

- [ ] **Step 3: Implement** — append to `backend/app/domain/auth.py`:

```python
from __future__ import annotations

import uuid

from itsdangerous import BadSignature, URLSafeSerializer

_SALT = "sift.auth.session"


def sign_session_id(session_id: uuid.UUID, *, secret: str) -> str:
    serializer = URLSafeSerializer(secret, salt=_SALT)
    return serializer.dumps(str(session_id))


def unsign_session_id(value: str, *, secret: str) -> uuid.UUID | None:
    if not value:
        return None
    serializer = URLSafeSerializer(secret, salt=_SALT)
    try:
        raw = serializer.loads(value)
    except BadSignature:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None
```

Note: keep the imports already at the top (`from __future__`, argon2) — only add what's missing. The single `from __future__` line at the top of the file is enough; do not duplicate it.

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/unit/test_auth_domain.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/auth.py backend/tests/unit/test_auth_domain.py
git commit -m "feat(auth): itsdangerous-signed session-id cookies"
```

---

## Task 4: Pydantic DTOs in `domain/auth.py`

**Files:**
- Modify: `backend/app/domain/auth.py`
- Modify: `backend/app/domain/models.py`
- Modify: `backend/tests/unit/test_auth_domain.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/unit/test_auth_domain.py`:

```python
import uuid as _uuid

from pydantic import ValidationError


class TestDTOs:
    def test_login_in_accepts_valid(self) -> None:
        from app.domain.auth import LoginIn

        body = LoginIn(email="ap-clerk@sift.demo", password="secret", remember=True)
        assert body.email == "ap-clerk@sift.demo"
        assert body.password == "secret"
        assert body.remember is True

    def test_login_in_rejects_bad_email(self) -> None:
        from app.domain.auth import LoginIn

        with pytest.raises(ValidationError):
            LoginIn(email="not-an-email", password="secret", remember=False)

    def test_login_in_rejects_empty_password(self) -> None:
        from app.domain.auth import LoginIn

        with pytest.raises(ValidationError):
            LoginIn(email="ap-clerk@sift.demo", password="", remember=False)

    def test_clerk_out_shape(self) -> None:
        from app.domain.auth import ClerkOut

        out = ClerkOut(
            id=_uuid.uuid4(),
            email="ap-clerk@sift.demo",
            display_name=None,
        )
        assert out.display_name is None
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/unit/test_auth_domain.py::TestDTOs -v
```

Expected: FAIL with `ImportError: cannot import name 'LoginIn'`.

- [ ] **Step 3: Implement** — append to `backend/app/domain/auth.py`:

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)
    remember: bool = False


class ClerkOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    display_name: str | None = None
```

- [ ] **Step 4: Re-export from `domain/models.py`** — append to the bottom of `backend/app/domain/models.py`:

```python
from app.domain.auth import ClerkOut, LoginIn  # noqa: F401, E402
```

This is the single seam that lets `scripts/generate_types.py` pick the auth DTOs up without changing the type-generation entry point.

- [ ] **Step 5: Run all unit tests + import-linter**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/unit/test_auth_domain.py -v
docker compose exec backend uv run lint-imports
```

Expected: all `test_auth_domain.py` pass; import-linter reports no broken contracts.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/auth.py backend/app/domain/models.py backend/tests/unit/test_auth_domain.py
git commit -m "feat(auth): LoginIn and ClerkOut DTOs"
```

---

## Task 5: Config additions

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add the new settings** to `backend/app/config.py` inside the `Settings` class, after `cors_origins_raw`:

```python
    secret_key: str = Field(
        default="dev-only-secret-do-not-use-in-prod",
        alias="SIFT_SECRET_KEY",
    )
    cookie_secure: bool = Field(default=False, alias="SIFT_COOKIE_SECURE")
    session_remember_days: int = Field(default=30, alias="SIFT_SESSION_REMEMBER_DAYS")
    session_default_hours: int = Field(default=12, alias="SIFT_SESSION_DEFAULT_HOURS")
    demo_email: str = Field(default="ap-clerk@sift.demo", alias="SIFT_DEMO_EMAIL")
    demo_password: str = Field(default="letmein-demo", alias="SIFT_DEMO_PASSWORD")
```

- [ ] **Step 2: Add a startup warning when the dev secret is in use** — add this method to `Settings`:

```python
    @property
    def using_dev_secret(self) -> bool:
        return self.secret_key == "dev-only-secret-do-not-use-in-prod"
```

Then in `backend/app/main.py`, inside `create_app()` right after `configure_logging(...)`, append:

```python
    if settings.using_dev_secret:
        import structlog

        structlog.get_logger().warning(
            "auth.dev_secret_in_use",
            hint="set SIFT_SECRET_KEY in production",
        )
```

- [ ] **Step 3: Update `.env.example`** — append:

```bash

# Auth — session cookie signing + demo user
SIFT_SECRET_KEY=dev-only-secret-do-not-use-in-prod
SIFT_COOKIE_SECURE=false
SIFT_SESSION_REMEMBER_DAYS=30
SIFT_SESSION_DEFAULT_HOURS=12
SIFT_DEMO_EMAIL=ap-clerk@sift.demo
SIFT_DEMO_PASSWORD=letmein-demo
```

- [ ] **Step 4: Smoke-load**

Run:
```bash
docker compose exec backend uv run python -c "from app.config import get_settings; s = get_settings(); print(s.demo_email, s.session_remember_days, s.using_dev_secret)"
```

Expected: `ap-clerk@sift.demo 30 True`

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/main.py .env.example
git commit -m "feat(config): auth settings — secret key, cookie flags, session expiry, demo creds"
```

---

## Task 6: ORM models — `User` and `AuthSession`

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Add the two ORM classes** — append to `backend/app/db/models.py`, after `FieldCorrection`:

```python
from sqlalchemy.dialects.postgresql import CITEXT


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    user: Mapped[User] = relationship(back_populates="sessions")
```

- [ ] **Step 2: Smoke-import the models**

Run:
```bash
docker compose exec backend uv run python -c "from app.db.models import User, AuthSession; print(User.__table__.columns.keys(), AuthSession.__table__.columns.keys())"
```

Expected: prints two column lists, one with `email`/`password_hash`, the other with `user_id`/`expires_at`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(db): User and AuthSession ORM models"
```

---

## Task 7: Alembic migration — `users` + `auth_sessions`

**Files:**
- Create: `backend/alembic/versions/<new>_add_users_and_auth_sessions.py`

- [ ] **Step 1: Find the current head revision**

Run:
```bash
docker compose exec backend uv run alembic heads
```

Note the revision id shown (e.g. `cf50d4a567b6`). Save it as `<PREV_HEAD>`.

- [ ] **Step 2: Generate a blank revision**

Run:
```bash
docker compose exec backend uv run alembic revision -m "add users and auth_sessions"
```

This creates a new file under `backend/alembic/versions/` named `<new>_add_users_and_auth_sessions.py`. Note its revision id as `<NEW_REV>`.

- [ ] **Step 3: Replace the contents of the new revision file** with:

```python
"""add users and auth_sessions

Revision ID: <NEW_REV>
Revises: <PREV_HEAD>
Create Date: <auto>

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "<NEW_REV>"
down_revision: str | Sequence[str] | None = "<PREV_HEAD>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
```

Replace `<NEW_REV>` and `<PREV_HEAD>` with the actual revision ids from Step 1-2. Leave `Create Date` as Alembic generated it.

- [ ] **Step 4: Apply the migration**

Run:
```bash
docker compose exec backend uv run alembic upgrade head
```

Expected: log lines `Running upgrade <PREV_HEAD> -> <NEW_REV>` with no error.

- [ ] **Step 5: Verify the tables**

Run:
```bash
docker compose exec -T db psql -U sift -d sift -c "\d users" -c "\d auth_sessions"
```

Expected: both tables described with the columns listed in Step 3 plus the indexes.

- [ ] **Step 6: Test the downgrade round-trip**

Run:
```bash
docker compose exec backend uv run alembic downgrade -1
docker compose exec -T db psql -U sift -d sift -c "\dt users" -c "\dt auth_sessions"
docker compose exec backend uv run alembic upgrade head
```

Expected: after downgrade, `\dt users` reports `Did not find any relation`. After upgrade, both tables reappear.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/<new>_add_users_and_auth_sessions.py
git commit -m "feat(db): migration adds users + auth_sessions tables"
```

---

## Task 8: `user_repo`

**Files:**
- Create: `backend/app/adapters/storage/user_repo.py`
- Test: `backend/tests/integration/test_auth_repos.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/integration/test_auth_repos.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.user_repo import (
    get_by_email,
    update_last_login,
    upsert_demo_user,
)
from app.domain.auth import hash_password, verify_password


class TestUserRepo:
    def test_upsert_creates_when_absent(self, db_session: Session) -> None:
        u = upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="secret-1",
        )
        assert u.id is not None
        assert verify_password("secret-1", u.password_hash)

    def test_upsert_is_idempotent_and_does_not_change_password(
        self, db_session: Session
    ) -> None:
        u1 = upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="secret-1",
        )
        u2 = upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="secret-2-different",
        )
        assert u1.id == u2.id
        assert verify_password("secret-1", u2.password_hash)
        assert not verify_password("secret-2-different", u2.password_hash)

    def test_get_by_email_is_case_insensitive(self, db_session: Session) -> None:
        upsert_demo_user(
            db_session,
            email="MixedCase@example.test",
            password="x",
        )
        found = get_by_email(db_session, "mixedcase@example.test")
        assert found is not None
        assert str(found.email).lower() == "mixedcase@example.test"

    def test_get_by_email_returns_none_when_absent(self, db_session: Session) -> None:
        assert get_by_email(db_session, "nobody@example.test") is None

    def test_update_last_login_writes_a_timestamp(self, db_session: Session) -> None:
        u = upsert_demo_user(
            db_session,
            email="lastlogin@example.test",
            password="x",
        )
        assert u.last_login_at is None
        update_last_login(db_session, user_id=u.id)
        db_session.refresh(u)
        assert u.last_login_at is not None
        assert (datetime.now(UTC) - u.last_login_at) < timedelta(seconds=5)
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_repos.py::TestUserRepo -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.adapters.storage.user_repo'`.

- [ ] **Step 3: Implement** — create `backend/app/adapters/storage/user_repo.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_repos.py::TestUserRepo -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/storage/user_repo.py backend/tests/integration/test_auth_repos.py
git commit -m "feat(auth): user_repo — get_by_email, update_last_login, upsert_demo_user"
```

---

## Task 9: `session_repo`

**Files:**
- Create: `backend/app/adapters/storage/session_repo.py`
- Modify: `backend/tests/integration/test_auth_repos.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/integration/test_auth_repos.py`:

```python
from app.adapters.storage.session_repo import (
    create as create_session,
    delete as delete_session,
    get_active as get_active_session,
    touch_last_seen,
)


class TestSessionRepo:
    def _user(self, db_session: Session):
        return upsert_demo_user(
            db_session,
            email="sess-tests@example.test",
            password="x",
        )

    def test_create_inserts_a_row(self, db_session: Session) -> None:
        user = self._user(db_session)
        expires = datetime.now(UTC) + timedelta(hours=12)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=expires,
            user_agent="pytest/1.0",
        )
        assert s.id is not None
        assert s.user_id == user.id
        assert s.expires_at == expires
        assert s.user_agent == "pytest/1.0"

    def test_get_active_returns_unexpired(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_agent=None,
        )
        found = get_active_session(db_session, s.id)
        assert found is not None
        assert found.id == s.id

    def test_get_active_returns_none_for_expired(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            user_agent=None,
        )
        assert get_active_session(db_session, s.id) is None

    def test_get_active_returns_none_for_unknown_id(self, db_session: Session) -> None:
        assert get_active_session(db_session, uuid4()) is None

    def test_delete_removes_row_and_is_idempotent(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_agent=None,
        )
        delete_session(db_session, s.id)
        assert get_active_session(db_session, s.id) is None
        delete_session(db_session, s.id)

    def test_touch_last_seen_updates_timestamp(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_agent=None,
        )
        original = s.last_seen_at
        touch_last_seen(db_session, s.id)
        db_session.refresh(s)
        assert s.last_seen_at > original
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_repos.py::TestSessionRepo -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — create `backend/app/adapters/storage/session_repo.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete, select, update
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
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_repos.py -v
```

Expected: 11 passed (5 user repo + 6 session repo).

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/storage/session_repo.py backend/tests/integration/test_auth_repos.py
git commit -m "feat(auth): session_repo — create, get_active, delete, touch_last_seen"
```

---

## Task 10: `auth_service.login()`

**Files:**
- Create: `backend/app/services/auth_service.py`
- Test: `backend/tests/integration/test_auth_service.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/integration/test_auth_service.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.auth_service'`.

- [ ] **Step 3: Implement** — create `backend/app/services/auth_service.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_service.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/integration/test_auth_service.py
git commit -m "feat(auth): auth_service.login — argon2 verify, session create, last-login touch"
```

---

## Task 11: `auth_service.resolve_session()`

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/tests/integration/test_auth_service.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/integration/test_auth_service.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_service.py::TestResolveSession -v
```

Expected: FAIL with `ImportError: cannot import name 'resolve_session'`.

- [ ] **Step 3: Implement** — append to `backend/app/services/auth_service.py`:

```python
from app.domain.auth import unsign_session_id


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
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_service.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/integration/test_auth_service.py
git commit -m "feat(auth): auth_service.resolve_session — verify cookie, cleanup expired"
```

---

## Task 12: `auth_service.logout()`

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/tests/integration/test_auth_service.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/integration/test_auth_service.py`:

```python
class TestLogout:
    def test_logout_deletes_session_row(self, db_session: Session) -> None:
        from app.services.auth_service import logout, resolve_session

        upsert_demo_user(db_session, email="logout@example.test", password="pw")
        outcome = login(
            db_session,
            email="logout@example.test",
            password="pw",
            remember=False,
            user_agent=None,
            secret=SECRET,
        )
        assert outcome is not None

        logout(db_session, outcome.signed_cookie, secret=SECRET)
        assert resolve_session(db_session, outcome.signed_cookie, secret=SECRET) is None

    def test_logout_no_cookie_is_a_noop(self, db_session: Session) -> None:
        from app.services.auth_service import logout

        logout(db_session, None, secret=SECRET)
        logout(db_session, "", secret=SECRET)

    def test_logout_invalid_cookie_is_a_noop(self, db_session: Session) -> None:
        from app.services.auth_service import logout

        logout(db_session, "not-a-real-cookie", secret=SECRET)
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_service.py::TestLogout -v
```

Expected: FAIL with `ImportError: cannot import name 'logout'`.

- [ ] **Step 3: Implement** — append to `backend/app/services/auth_service.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_service.py -v
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/integration/test_auth_service.py
git commit -m "feat(auth): auth_service.logout — delete session row, idempotent"
```

---

## Task 13: API dependency `get_current_clerk`

**Files:**
- Create: `backend/app/api/deps.py`

- [ ] **Step 1: Implement** — create `backend/app/api/deps.py`:

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.domain.auth import ClerkOut
from app.services.auth_service import resolve_session

SESSION_COOKIE_NAME = "sift_session"


def get_current_clerk(
    request: Request,
    session: Session = Depends(get_session),
) -> ClerkOut:
    signed = request.cookies.get(SESSION_COOKIE_NAME)
    clerk = resolve_session(session, signed, secret=get_settings().secret_key)
    if clerk is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return clerk
```

- [ ] **Step 2: Add the new api modules to the import-linter allow-list** — both `app.api.deps` and the upcoming `app.api.auth` need to import `app.db.session.get_session` (FastAPI DI glue, same pattern as the existing routes). Edit `backend/pyproject.toml` and replace the third contract's `ignore_imports` block with:

```toml
ignore_imports = [
    "app.api.invoices -> app.db.session",
    "app.api.search -> app.db.session",
    "app.api.deps -> app.db.session",
    "app.api.auth -> app.db.session",
]
```

- [ ] **Step 3: Verify import boundaries**

```bash
docker compose exec backend uv run lint-imports
```

Expected: all contracts pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/deps.py backend/pyproject.toml
git commit -m "feat(auth): get_current_clerk FastAPI dependency"
```

---

## Task 14: API router — login/logout/me

**Files:**
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_auth_api.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/integration/test_auth_api.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage.user_repo import upsert_demo_user


SESSION_COOKIE = "sift_session"


def _seed_demo_user(db_session: Session) -> None:
    upsert_demo_user(
        db_session,
        email="ap-clerk@sift.demo",
        password="letmein-demo",
    )


class TestLogin:
    def test_login_success_sets_cookie_and_returns_user(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["user"]["email"].lower() == "ap-clerk@sift.demo"
        assert SESSION_COOKIE in res.cookies

    def test_login_wrong_password_returns_401_generic(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "wrong",
                "remember": False,
            },
        )
        assert res.status_code == 401
        assert res.json() == {"detail": "Email or password incorrect."}
        assert SESSION_COOKIE not in res.cookies

    def test_login_unknown_email_returns_same_message(self, unauthed_client) -> None:
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "nobody@example.test",
                "password": "x",
                "remember": False,
            },
        )
        assert res.status_code == 401
        assert res.json() == {"detail": "Email or password incorrect."}

    def test_login_invalid_payload_returns_422(self, unauthed_client) -> None:
        res = unauthed_client.post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "x", "remember": False},
        )
        assert res.status_code == 422

    def test_login_remember_sets_max_age(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": True,
            },
        )
        assert res.status_code == 200
        set_cookie = res.headers["set-cookie"]
        assert "Max-Age=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=Lax" in set_cookie


class TestMe:
    def test_me_without_cookie_is_401(self, unauthed_client) -> None:
        res = unauthed_client.get("/api/auth/me")
        assert res.status_code == 401

    def test_me_with_cookie_returns_clerk(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        login_res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        assert login_res.status_code == 200
        me_res = unauthed_client.get("/api/auth/me")
        assert me_res.status_code == 200
        body = me_res.json()
        assert body["email"].lower() == "ap-clerk@sift.demo"


class TestLogout:
    def test_logout_clears_cookie_and_invalidates_session(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        res = unauthed_client.post("/api/auth/logout")
        assert res.status_code == 204

        me_res = unauthed_client.get("/api/auth/me")
        assert me_res.status_code == 401

    def test_logout_without_cookie_is_204(self, unauthed_client) -> None:
        res = unauthed_client.post("/api/auth/logout")
        assert res.status_code == 204
```

These tests use a fixture called `unauthed_client` that does NOT exist yet. The next step adds it as a temporary alias of the current `api_client` so the test suite still runs while we build the endpoints. Task 16 reorganizes this.

- [ ] **Step 2: Add a temporary `unauthed_client` fixture** — append to `backend/tests/integration/conftest.py`:

```python
@pytest.fixture
def unauthed_client(api_client: TestClient) -> TestClient:
    return api_client
```

- [ ] **Step 3: Run to verify the tests fail with the right errors**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_api.py -v
```

Expected: most fail with 404 (no `/api/auth/*` route registered yet).

- [ ] **Step 4: Implement the router** — create `backend/app/api/auth.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME, get_current_clerk
from app.config import get_settings
from app.db.session import get_session
from app.domain.auth import ClerkOut, LoginIn
from app.services.auth_service import login as login_service, logout as logout_service

router = APIRouter()


class LoginResponse(BaseModel):
    user: ClerkOut


@router.post("/login", response_model=LoginResponse)
def login_endpoint(
    body: LoginIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    settings = get_settings()
    outcome = login_service(
        session,
        email=body.email,
        password=body.password,
        remember=body.remember,
        user_agent=request.headers.get("user-agent"),
    )
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password incorrect.",
        )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=outcome.signed_cookie,
        max_age=outcome.max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(user=outcome.clerk)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> None:
    logout_service(session, request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=ClerkOut)
def me_endpoint(clerk: ClerkOut = Depends(get_current_clerk)) -> ClerkOut:
    return clerk
```

- [ ] **Step 5: Register the router in `app/main.py`** — modify `backend/app/main.py:76-79`. Change:

```python
    from app.api import invoices, search

    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
```

to:

```python
    from app.api import auth, invoices, search

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
```

- [ ] **Step 6: Run the auth API tests**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_api.py -v
```

Expected: 9 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/app/main.py backend/tests/integration/test_auth_api.py backend/tests/integration/conftest.py
git commit -m "feat(api): auth router — POST /login, POST /logout, GET /me"
```

---

## Task 15: Gate `api/invoices.py` + flip `api_client` to authed by default

This task combines two concerns so that the test suite stays green at every commit boundary: gating the existing routes forces every test to provide auth, and the simplest path is to make the shared `api_client` fixture provide it.

**Files:**
- Modify: `backend/app/api/invoices.py`
- Modify: `backend/tests/integration/conftest.py`

- [ ] **Step 1: Make `api_client` authed by default** — replace the entire `backend/tests/integration/conftest.py` with:

```python
"""Integration test isolation — savepoint-wrapped sessions for API tests.

`api_client` is authenticated as a seeded test clerk. Tests that need to
exercise the 401 path use `unauthed_client` instead.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.adapters.storage.session_repo import create as create_session
from app.adapters.storage.user_repo import upsert_demo_user
from app.config import get_settings
from app.db.session import engine, get_session
from app.domain.auth import sign_session_id
from app.main import app


def _build_client(authed: bool) -> Generator[TestClient, None, None]:
    connection = engine.connect()
    outer_txn = connection.begin()
    session = Session(
        bind=connection, autocommit=False, autoflush=False, expire_on_commit=False
    )
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(_session: Session, transaction) -> None:
        nonlocal nested
        if transaction.nested and not transaction._parent.nested:
            nested = connection.begin_nested()

    def _override_get_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as client:
            if authed:
                user = upsert_demo_user(
                    session,
                    email="test-clerk@example.test",
                    password="test-password",
                )
                auth_session = create_session(
                    session,
                    user_id=user.id,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    user_agent="pytest",
                )
                signed = sign_session_id(
                    auth_session.id, secret=get_settings().secret_key
                )
                client.cookies.set("sift_session", signed)
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        session.close()
        if outer_txn.is_active:
            outer_txn.rollback()
        connection.close()


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    yield from _build_client(authed=True)


@pytest.fixture
def unauthed_client() -> Generator[TestClient, None, None]:
    yield from _build_client(authed=False)
```

- [ ] **Step 2: Run the full integration suite — existing tests should still pass**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration -v
```

Expected: all existing tests pass (the new authed fixture doesn't break them because routes are not yet gated). The previously written `test_auth_api.py` continues to pass because it uses `unauthed_client`.

- [ ] **Step 3: Write the failing regression test** — append to `backend/tests/integration/test_invoices_api.py`:

```python
class TestAuthGate:
    def test_list_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.get("/api/invoices")
        assert res.status_code == 401

    def test_upload_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.post(
            "/api/invoices",
            files={"file": ("x.pdf", b"%PDF-", "application/pdf")},
        )
        assert res.status_code == 401
```

- [ ] **Step 4: Run to verify the gate tests fail (no auth yet)**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_invoices_api.py::TestAuthGate -v
```

Expected: FAIL with 415 (upload) and 200 (list) — neither is 401 yet.

- [ ] **Step 5: Gate every endpoint in `backend/app/api/invoices.py`** — add an import and a guard dependency to each route.

At the top, add to existing imports:

```python
from app.api.deps import get_current_clerk
from app.domain.auth import ClerkOut
```

Then in every `@router.*`-decorated function, add `_clerk: ClerkOut = Depends(get_current_clerk),` **after any path/positional parameters (e.g. `invoice_id: UUID`, `file: UploadFile = File(...)`) and before `session: Session = Depends(get_session),`**. Python syntax forbids placing keyword-defaulted parameters before required ones; respect that ordering.

Examples:

```python
@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def upload_invoice(
    file: UploadFile = File(...),
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    ...

@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice_endpoint(
    invoice_id: UUID,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    ...
```

Apply the same pattern to: `list_invoices_endpoint`, `get_invoice_endpoint`, `serve_invoice_pdf`, `get_invoice_vendor`, `confirm_endpoint`, `dismiss_endpoint`, `unprocessable_endpoint`, `retry_endpoint`. **Every** `@router.*`-decorated function gets the new dependency.

- [ ] **Step 6: Run the full suite**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration -v
```

Expected: all passing. `TestAuthGate` returns 401. Existing tests still pass because `api_client` carries the cookie.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/invoices.py backend/tests/integration/conftest.py backend/tests/integration/test_invoices_api.py
git commit -m "feat(api): gate invoices routes behind get_current_clerk"
```

---

## Task 16: Gate `api/search.py`

**Files:**
- Modify: `backend/app/api/search.py`
- Modify: `backend/tests/integration/test_search.py`

- [ ] **Step 1: Write the failing regression test** — append to `backend/tests/integration/test_search.py`:

```python
class TestAuthGate:
    def test_search_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.post("/api/search", json={"filters": []})
        assert res.status_code == 401

    def test_translate_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.post("/api/search/translate", json={"text": "x"})
        assert res.status_code == 401
```

If the existing `test_search.py` does not import or otherwise reference `unauthed_client` yet, no additional change is needed — fixtures are picked up from `conftest.py`.

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_search.py::TestAuthGate -v
```

Expected: not 401 (the routes are still open).

- [ ] **Step 3: Read the existing endpoints** to see their full signatures

```bash
docker compose exec backend uv run python -c "import app.api.search as s; print(open(s.__file__).read())" | head -80
```

- [ ] **Step 4: Gate every endpoint in `backend/app/api/search.py`** — same pattern as Task 15: add the import and inject `_clerk: ClerkOut = Depends(get_current_clerk)` as the first parameter of every `@router.*`-decorated function.

- [ ] **Step 5: Run the full integration suite**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/search.py backend/tests/integration/test_search.py
git commit -m "feat(api): gate search routes behind get_current_clerk"
```

---

## Task 17: Seed the demo user in `scripts/seed_demo.py`

**Files:**
- Modify: `backend/scripts/seed_demo.py`
- Test: extend `backend/tests/integration/test_auth_repos.py`

- [ ] **Step 1: Add an idempotency test for the seed function** — append to `backend/tests/integration/test_auth_repos.py`:

```python
class TestSeedDemoUser:
    def test_seed_demo_user_is_idempotent_and_does_not_change_password(
        self, db_session: Session
    ) -> None:
        from scripts.seed_demo import seed_demo_user
        from app.config import get_settings

        settings = get_settings()
        u1 = seed_demo_user(db_session)
        assert u1.email == settings.demo_email
        assert verify_password(settings.demo_password, u1.password_hash)

        u2 = seed_demo_user(db_session)
        assert u1.id == u2.id
```

Note: `scripts.seed_demo` is importable because pytest runs inside the backend container where the working directory is `/app/backend` and both `app/` and `scripts/` are top-level packages.

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_repos.py::TestSeedDemoUser -v
```

Expected: FAIL with `ImportError: cannot import name 'seed_demo_user'`.

- [ ] **Step 3: Add `seed_demo_user` to `backend/scripts/seed_demo.py`** — near the top of the file (after imports, before `SEEDS`):

```python
from app.adapters.storage.user_repo import upsert_demo_user
from app.db.models import User


def seed_demo_user(session) -> User:
    settings = get_settings()
    return upsert_demo_user(
        session,
        email=settings.demo_email,
        password=settings.demo_password,
    )
```

Then call it at the top of `main()`, right after `session = SessionLocal()` and before the `try:`:

```python
    seed_demo_user(session)
    log.info("seeded demo user %s", get_settings().demo_email)
```

- [ ] **Step 4: Run to verify it passes**

Run:
```bash
docker compose exec backend uv run pytest backend/tests/integration/test_auth_repos.py::TestSeedDemoUser -v
```

Expected: 1 passed.

- [ ] **Step 5: Smoke `make demo`**

Run:
```bash
make demo
```

Expected: completes without error and prints `seeded demo user ap-clerk@sift.demo`. Spot-check: `docker compose exec -T db psql -U sift -d sift -c "SELECT email FROM users;"` returns one row.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/seed_demo.py backend/tests/integration/test_auth_repos.py
git commit -m "feat(seed): seed demo user from config on demo runs"
```

---

## Task 18: Production secrets note in `DEPLOY.md`

**Files:**
- Modify: `DEPLOY.md`

- [ ] **Step 1: Append a new section** — at the end of `DEPLOY.md`:

```markdown

## Auth — required Fly secrets

The login backend needs two secrets set on the Fly app before first deploy:

```bash
fly secrets set SIFT_SECRET_KEY="$(openssl rand -hex 32)"
fly secrets set SIFT_COOKIE_SECURE=true
```

The demo user is seeded automatically by `make demo` (using
`SIFT_DEMO_EMAIL` / `SIFT_DEMO_PASSWORD`). If you want a different demo
email or password in prod, also set those secrets before running the
seed:

```bash
fly secrets set SIFT_DEMO_EMAIL="..." SIFT_DEMO_PASSWORD="..."
```

The seed function is idempotent — re-running `make demo` will not reset
an existing demo user's password.
```

- [ ] **Step 2: Commit**

```bash
git add DEPLOY.md
git commit -m "docs(deploy): production secrets for login backend"
```

---

## Task 19: Regenerate frontend types

**Files:**
- Modify: `frontend/src/types/generated/domain.ts`

- [ ] **Step 1: Run the generator**

```bash
docker compose exec backend uv run python scripts/generate_types.py
```

Expected: file updated.

- [ ] **Step 2: Verify the new types are present**

```bash
grep -E "ClerkOut|LoginIn" frontend/src/types/generated/domain.ts
```

Expected: both names appear as `export interface ClerkOut { ... }` and `export interface LoginIn { ... }`.

- [ ] **Step 3: Run the frontend type check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/generated/domain.ts
git commit -m "chore(types): regenerate frontend types — ClerkOut, LoginIn"
```

---

## Task 20: Frontend API client — credentials + 401 handler

**Files:**
- Modify: `frontend/src/state/api.ts`

- [ ] **Step 1: Replace the contents of `frontend/src/state/api.ts`** with:

```ts
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body?: unknown
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type UnauthorizedHandler = () => void

let unauthorizedHandler: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
  })
  if (!res.ok) {
    if (res.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    let body: unknown
    try {
      body = await res.json()
    } catch {
      body = await res.text().catch(() => undefined)
    }
    throw new ApiError(
      res.status,
      `${init?.method ?? 'GET'} ${path} → ${res.status}`,
      body
    )
  }
  if (res.status === 204) {
    return undefined as unknown as T
  }
  return res.json() as Promise<T>
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: clean. (Existing call sites need no change — the new fields are optional.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/state/api.ts
git commit -m "feat(frontend): always send credentials, pluggable 401 handler"
```

---

## Task 21: Frontend auth hooks

**Files:**
- Create: `frontend/src/state/auth.ts`

- [ ] **Step 1: Implement** — create `frontend/src/state/auth.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/state/api'
import type { ClerkOut, LoginIn } from '@/types/generated/domain'

const ME_KEY = ['auth', 'me'] as const

export function useMeQuery() {
  return useQuery<ClerkOut | null, ApiError>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api<ClerkOut>('/api/auth/me')
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          return null
        }
        throw err
      }
    },
    retry: false,
    staleTime: 30_000,
  })
}

export function useLoginMutation() {
  const qc = useQueryClient()
  return useMutation<{ user: ClerkOut }, ApiError, LoginIn>({
    mutationFn: (body) =>
      api<{ user: ClerkOut }>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: ({ user }) => {
      qc.setQueryData(ME_KEY, user)
    },
  })
}

export function useLogoutMutation() {
  const qc = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      qc.setQueryData(ME_KEY, null)
      qc.clear()
    },
  })
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/state/auth.ts
git commit -m "feat(frontend): auth hooks — useMeQuery, useLoginMutation, useLogoutMutation"
```

---

## Task 22: Wire `LoginScreen` to the backend

**Files:**
- Modify: `frontend/src/routes/LoginScreen.tsx`

- [ ] **Step 1: Replace the `LoginScreen` function in `frontend/src/routes/LoginScreen.tsx`** — keep everything above `export function LoginScreen()` (the icon components, `ARROW_PATH`, `PreviewRow`) and replace only the `LoginScreen` function body. The new top of the function should look like this; preserve the JSX below from the existing file unchanged except for the two specific edits called out below.

Replace the top of `LoginScreen` (currently lines ~102-125):

```tsx
export function LoginScreen() {
  const navigate = useNavigate()
  const loginMutation = useLoginMutation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
    if (!meta) return
    const original = meta.content
    meta.content = 'width=device-width, initial-scale=1'
    return () => {
      meta.content = original
    }
  }, [])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!email.trim() || !password) return
    setErrorMessage(null)
    loginMutation.mutate(
      { email: email.trim(), password, remember },
      {
        onSuccess: () => {
          navigate('/inbox', { replace: true })
        },
        onError: (err) => {
          const detail =
            err.status === 401
              ? 'Email or password incorrect.'
              : 'Something went wrong. Try again.'
          setErrorMessage(detail)
        },
      },
    )
  }
```

Add the import at the top of the file:

```tsx
import { useLoginMutation } from '@/state/auth'
```

- [ ] **Step 2: Render the error message** — find the password field block (the `<div className="mt-3.5 flex flex-col gap-1.5">` containing the password input, around line 235-272 in the existing file). Directly after that closing `</div>`, before the "remember" checkbox row, insert:

```tsx
            {errorMessage ? (
              <div
                role="alert"
                className="mt-2 text-[12.5px] leading-[1.5] text-aside-review"
              >
                {errorMessage}
              </div>
            ) : null}
```

- [ ] **Step 3: Disable the submit button while the mutation is pending** — find the existing submit button (around line 302-308). Add `disabled={loginMutation.isPending}` and adjust its label:

```tsx
            <button
              type="submit"
              disabled={loginMutation.isPending}
              className="mt-[22px] flex w-full flex-nowrap items-center justify-center gap-2 whitespace-nowrap border-0 bg-action px-4 py-3.5 text-[15px] font-semibold tracking-[-0.005em] text-white transition-all duration-100 hover:bg-action-focus active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-ink-48 max-md:py-[15px] max-md:text-[15.5px]"
            >
              <span>{loginMutation.isPending ? 'Signing in…' : 'Sign in'}</span>
              <ArrowIcon />
            </button>
```

- [ ] **Step 4: Type-check + run the dev server**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: clean.

Then manually verify in a browser (`make dev` or `pnpm dev`):
1. Bad creds → inline error "Email or password incorrect."
2. Good creds (`ap-clerk@sift.demo` / `letmein-demo`) → navigate to `/inbox`.
3. Submit button shows "Signing in…" while pending.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/LoginScreen.tsx
git commit -m "feat(login): wire form to /api/auth/login with inline error"
```

---

## Task 23: `Shell` boot guard + sign-out

**Files:**
- Modify: `frontend/src/components/shell/Shell.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Register a global 401 handler in `frontend/src/main.tsx`**.

Add this `import` after the existing `import { router } from '@/routes/router'` line:

```tsx
import { setUnauthorizedHandler } from '@/state/api'
```

Then, immediately after the `const queryClient = new QueryClient({...})` block and before the `ReactDOM.createRoot(...)` call, add:

```tsx
setUnauthorizedHandler(() => {
  queryClient.clear()
  if (window.location.pathname !== '/login') {
    window.location.replace('/login')
  }
})
```

Clearing the query cache on 401 prevents stale `me` data from sticking around after the redirect.

- [ ] **Step 2: Add a boot guard to `frontend/src/components/shell/Shell.tsx`** — modify the top of the `Shell()` function (after the existing `useNavigate()` line) to add an auth check using the existing TanStack Query setup:

```tsx
  const { data: me, isLoading: meLoading } = useMeQuery()
  const logout = useLogoutMutation()

  if (meLoading) {
    return (
      <div className="grid h-screen place-items-center bg-canvas text-ink-60 text-sm">
        Loading…
      </div>
    )
  }
  if (!me) {
    return <Navigate to="/login" replace />
  }
```

Add the imports at the top of the file:

```tsx
import { Navigate } from 'react-router-dom'

import { useLogoutMutation, useMeQuery } from '@/state/auth'
```

(If `Navigate` is already imported from `react-router-dom`, just add it to the existing import statement.)

- [ ] **Step 3: Add a sign-out control above the sidebar footer** — find the existing `.sidebar-footer` block (`Shell.tsx:128-131`) and replace it with:

```tsx
        <div className="sidebar-footer">
          <button
            type="button"
            onClick={() => {
              logout.mutate(undefined, {
                onSettled: () => navigate('/login', { replace: true }),
              })
            }}
            className="text-left text-[12px] tracking-[-0.005em] text-light-subtle hover:text-light underline-offset-2 hover:underline disabled:cursor-not-allowed"
            disabled={logout.isPending}
          >
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </button>
          <span className="sidebar-footer-dot" />
          <span>All systems normal · Haiku 4.5 / Sonnet 4.6</span>
        </div>
```

The existing CSS class `sidebar-footer` is a flex row in `index.css`; adding a button at the start is consistent with the row layout.

- [ ] **Step 4: Type-check + run the dev server**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: clean.

Manual smoke:
1. Hit `/inbox` directly without logging in → bounces to `/login`.
2. Log in → lands on `/inbox`.
3. Click "Sign out" → bounces back to `/login`, `/inbox` is no longer reachable.
4. With a valid session, refresh the page on `/inbox` → no flash to login.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/components/shell/Shell.tsx
git commit -m "feat(shell): boot guard via /api/auth/me + sign-out control"
```

---

## Task 24: End-to-end verification

**Files:**
- Read-only verification across the whole repo.

- [ ] **Step 1: Run the full backend test suite**

```bash
docker compose exec backend uv run pytest -v
```

Expected: all pass. New tests in `test_auth_domain.py`, `test_auth_repos.py`, `test_auth_service.py`, `test_auth_api.py`, plus the gate tests in `test_invoices_api.py` and `test_search.py`.

- [ ] **Step 2: Run the import-linter**

```bash
docker compose exec backend uv run lint-imports
```

Expected: all contracts pass.

- [ ] **Step 3: Run ruff**

```bash
docker compose exec backend uv run ruff check .
```

Expected: clean.

- [ ] **Step 4: Run the frontend type-check**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 5: Demo walkthrough**

```bash
make demo
make dev   # or whatever brings up backend+frontend in dev mode
```

Then in a browser:
1. Visit `/inbox` cold → redirected to `/login`.
2. Submit empty form → no submission (HTML5 required).
3. Wrong password → inline 401 error, no navigation.
4. Correct creds (`ap-clerk@sift.demo` / `letmein-demo`) → land on `/inbox`.
5. Refresh `/inbox` → stays on `/inbox`.
6. Click "Sign out" in sidebar → back to `/login`.
7. Hit any deep link like `/invoice/some-id` while logged out → bounced to `/login`.

- [ ] **Step 6: Final commit (only if any housekeeping changes are needed)**

If steps 1-5 turned up no follow-ups, skip. Otherwise group the housekeeping into a single commit with a descriptive message.

---

## Coverage Map (plan → spec)

| Spec section            | Tasks                        |
| ----------------------- | ---------------------------- |
| Data model              | 6, 7                         |
| Endpoints (login/me/logout) | 14                       |
| Cookie attributes       | 3, 14                        |
| Route protection        | 13, 15, 16                   |
| Layer placement         | 2-4, 8-12, 13, 14            |
| Code style — comments   | (rule referenced in header)  |
| Config                  | 5                            |
| Seed                    | 17                           |
| Frontend integration    | 19, 20, 21, 22, 23           |
| Errors and edge cases   | 10, 11, 14                   |
| Testing                 | 2-4, 8-12, 14, 15, 16, 17, 24 |
| Migration               | 7                            |
| Out of scope            | (no code; not implemented)   |

Every spec requirement maps to at least one task. Stub links (`Request access`, `Forgot password?`) remain `href="#"` per spec.
