# Login backend — design

**Status:** approved
**Date:** 2026-05-15
**Scope:** Wire the existing `LoginScreen.tsx` UI to a real backend. Add a
single-clerk auth system that matches Sift's "one AP Clerk" framing, fits the
layered architecture from [ADR-0005](../../adr/0005-layered-architecture.md),
and gates the existing protected routes.

## Why

`frontend/src/routes/LoginScreen.tsx` collects email/password/remember and
calls `navigate('/inbox')` with no backend call. The other routes are wrapped
in `<Shell />` with zero protection. We need just enough auth to make the
demo feel real end-to-end — not multi-tenant SaaS.

## Decision

Server-side sessions, HttpOnly cookie, single demo user seeded from env. The
`users` table is shaped for future per-user features (correction attribution,
multi-user) without committing to building them now.

Rejected alternatives:

- **JWT in cookie, stateless.** Saves a `auth_sessions` table; loses
  revocation without adding a denylist. Step away from "Postgres holds all
  state" — not worth ~20 LOC.
- **Env-only credentials, no DB user.** Tempting given Sift's
  single-clerk framing, but throws away the audit hook (`corrected_by_user_id`
  on `field_corrections`) for negligible savings.

## Data model

New tables, one Alembic revision, enables `citext` extension.

### `users`

| column           | type        | notes                                     |
| ---------------- | ----------- | ----------------------------------------- |
| `id`             | `uuid` PK   | `uuid_generate_v4()` default              |
| `email`          | `citext`    | unique, not null                          |
| `password_hash`  | `text`      | argon2 encoded string, not null           |
| `display_name`   | `text`      | nullable                                  |
| `created_at`     | `timestamptz` | server default `now()`, not null        |
| `last_login_at`  | `timestamptz` | nullable                                |

### `auth_sessions`

| column         | type            | notes                                  |
| -------------- | --------------- | -------------------------------------- |
| `id`           | `uuid` PK       | this is the session id put in the cookie |
| `user_id`      | `uuid` FK users | not null, indexed                      |
| `created_at`   | `timestamptz`   | server default `now()`, not null       |
| `expires_at`   | `timestamptz`   | not null, indexed                      |
| `last_seen_at` | `timestamptz`   | server default `now()`, not null       |
| `user_agent`   | `text`          | nullable, debug only                   |

Naming the ORM class `AuthSession` avoids visual collision with
`sqlalchemy.orm.Session`.

## Endpoints

### `POST /api/auth/login`

- Body: `LoginIn { email: EmailStr, password: str, remember: bool }`.
- On success: insert `auth_sessions`, set `sift_session` cookie, update
  `users.last_login_at`, return `{ user: ClerkOut }` with 200.
- On failure: 401 with `{"detail": "Email or password incorrect."}` — same
  body for "no such user" and "wrong password" to avoid enumeration.
- Argon2 verify uses `argon2-cffi`. Verification runs even when the user
  doesn't exist (compare against a fixed dummy hash) to keep response time
  flat across the two failure modes.

### `POST /api/auth/logout`

- Reads cookie. If present and valid, deletes the matching `auth_sessions`
  row. Always clears the cookie. Returns 204.

### `GET /api/auth/me`

- Returns `ClerkOut` if a valid session resolves, else 401. Used by `Shell`
  on app boot.

`ClerkOut`: `{ id: UUID, email: str, display_name: str | None }`.

## Cookie

- Name: `sift_session`.
- Value: session UUID signed with `itsdangerous.URLSafeSerializer` keyed by
  `SIFT_SECRET_KEY`. Signing is defense-in-depth; tampered cookies are
  rejected without a DB roundtrip.
- Attributes: `HttpOnly`, `SameSite=Lax`, `Path=/`. `Secure` when
  `SIFT_COOKIE_SECURE=true` (production).
- Expiry:
  - `remember=true` (page default) → cookie `Max-Age = 30 days`,
    `auth_sessions.expires_at = now + 30 days`.
  - `remember=false` → session cookie (no `Max-Age`, dies with browser),
    `auth_sessions.expires_at = now + 12 hours`.
- No sliding refresh. `last_seen_at` is touched on each resolved request for
  debug visibility only; `expires_at` is set at session creation and never
  extended.

CORS already runs with `allow_credentials=True`; the frontend uses
`credentials: 'include'`.

## Route protection

`api/deps.py` exposes a `get_current_clerk` FastAPI dependency that:

1. Reads `sift_session` from the request.
2. Calls `auth_service.resolve_session(session, signed_value)`.
3. Returns `ClerkOut`, or raises `HTTPException(401)` on missing/invalid/
   expired sessions.

Added to **all** existing routes in `api/invoices.py` and `api/search.py`.
Public endpoints (`/health`, `/api/meta`, `/api/auth/*`) stay open.

`current_clerk` is **not** plumbed into the service layer. Sift has no
per-user data yet; threading `user_id` through `extract_and_serialize`,
`bulk_confirm_invoices`, etc. is premature. The dependency is a gate at the
API edge. When per-user audit lands, service signatures change then.

## Layer placement (per ADR-0005)

```
backend/app/
├── domain/auth.py            # ClerkOut, LoginIn; hash_password, verify_password
├── services/auth_service.py  # login(), logout(), resolve_session()
├── adapters/storage/
│   ├── user_repo.py          # get_by_email, update_last_login
│   └── session_repo.py       # create, get_active, delete, touch
├── api/
│   ├── auth.py               # POST /login, POST /logout, GET /me
│   └── deps.py               # get_current_clerk
├── db/models.py              # + User, AuthSession ORM
└── alembic/versions/         # users + auth_sessions + citext migration
```

Argon2 hashing lives in `domain/auth.py` — pure CPU, no IO, keeps unit tests
fixture-free. The existing import-linter contracts in `pyproject.toml` cover
the new paths without edits.

## Config

Additions to [`app/config.py`](../../../backend/app/config.py):

| setting                  | env var                  | default                | notes |
| ------------------------ | ------------------------ | ---------------------- | ----- |
| `secret_key`             | `SIFT_SECRET_KEY`        | dev-only fallback with startup warning | required in prod |
| `cookie_secure`          | `SIFT_COOKIE_SECURE`     | `false`                | `true` on Fly  |
| `session_remember_days`  | —                        | `30`                   |       |
| `session_default_hours`  | —                        | `12`                   |       |
| `demo_email`             | `SIFT_DEMO_EMAIL`        | `ap-clerk@sift.demo`   | seed only |
| `demo_password`          | `SIFT_DEMO_PASSWORD`     | `letmein-demo`         | seed only |

Add the new keys to `.env.example`. Add a `DEPLOY.md` note: set
`SIFT_SECRET_KEY` and `SIFT_COOKIE_SECURE=true` on the Fly app.

## Seed

Extend the existing seed script (the one invoked by `make seed-demo` /
`make demo`) with a `seed_demo_user(session)` step:

- Upsert by `email = settings.demo_email`. If the row exists, leave it
  alone (don't re-hash the password on every reset-db).
- On insert: hash `settings.demo_password` with argon2 and store.

## Frontend integration

The task is backend, but four small frontend changes are required to make
the system real:

1. **`LoginScreen.handleSubmit`** ([LoginScreen.tsx:119](../../../frontend/src/routes/LoginScreen.tsx)) —
   replace `navigate('/inbox')` with `POST /api/auth/login` (use
   `credentials: 'include'`). On 401, show an inline error under the
   password field using the existing tone language (single line in
   `text-aside-review` or similar). On success, navigate to `/inbox`.
2. **`Shell` boot guard** — `GET /api/auth/me` on mount via TanStack Query.
   While loading, render a minimal splash; on 401, `<Navigate to="/login"
   replace />`.
3. **Global 401 interceptor** — wrap the existing fetch/query layer so any
   401 from a protected route invalidates the cache and redirects to
   `/login`.
4. **Sign-out affordance** — small "Sign out" control in or directly above
   the existing `.sidebar-footer` block in
   [`Shell.tsx`](../../../frontend/src/components/shell/Shell.tsx) (the
   `"All systems normal · Haiku 4.5 / Sonnet 4.6"` row). Calls `POST
   /api/auth/logout`, then `navigate('/login', { replace: true })`.

`ClerkOut` and `LoginIn` flow through the existing
`pydantic-to-typescript` build step so frontend types stay generated.

The stub links on `LoginScreen` (`Request access`, `Forgot password?`,
`Trouble signing in?`, `support@sift.app`) stay as `href="#"`.

## Errors and edge cases

| case | behavior |
| ---- | -------- |
| unknown email | 401, generic message, dummy-hash verify to flatten timing |
| wrong password | 401, generic message |
| empty email or password | 422 from Pydantic validation on `LoginIn` |
| valid cookie, expired row | 401, cookie cleared, session row deleted |
| valid cookie, deleted row | 401, cookie cleared |
| valid cookie, valid row | request proceeds, `last_seen_at` touched |
| tampered cookie | 401, cookie cleared, no DB hit |
| no cookie on `/me` or protected route | 401 |

`last_seen_at` updates use a single `UPDATE` with no read-modify-write. We
don't block on it; if it fails we still serve the request.

## Testing

Unit tests in `tests/unit/`:

- `domain/auth.py`: argon2 hash + verify round-trip; verify rejects wrong
  password; `LoginIn` rejects empty fields and bad emails.
- Itsdangerous sign/unsign round-trip; tampered payload raises.

Integration tests in `tests/integration/` using the existing transaction-
rollback fixture and FastAPI `TestClient`:

- login success → 200, `set-cookie` present, one row in `auth_sessions`.
- login wrong password → 401, no row inserted.
- login unknown email → 401, no row inserted.
- `GET /me` with cookie → 200 with `ClerkOut`.
- `GET /me` without cookie → 401.
- `GET /api/invoices` without cookie → 401 (regression guard for new
  dependency on existing routes).
- `GET /api/invoices` with cookie → 200 (current behavior preserved).
- Logout → 204, cookie cleared, session row gone, next `/me` → 401.
- Expired `auth_sessions.expires_at` (use a time helper) → 401 and row
  cleaned up.

## Migration

New Alembic revision:

- `CREATE EXTENSION IF NOT EXISTS citext;`
- `CREATE TABLE users (...)` with unique constraint on `email`.
- `CREATE TABLE auth_sessions (...)` with FK to `users(id)` `ON DELETE
  CASCADE`.
- Indexes: `auth_sessions(user_id)`, `auth_sessions(expires_at)`.
- Down: drop both tables. Leave `citext` installed (other tables may grow
  to use it).

## Out of scope

- Signup / Request access flow.
- Forgot password / Trouble signing in.
- Email verification, MFA, OAuth/SSO.
- Rate limiting on `/login` (future: slowapi or reverse-proxy).
- CSRF tokens — relying on `SameSite=Lax` + same-origin. `POST
  /api/invoices` accepts `multipart/form-data`, but `SameSite=Lax` blocks
  the session cookie on cross-site form POSTs regardless of content type.
- Session sliding refresh.
- Multi-user UI (no user management screen, no role model).
- Per-record audit attribution (schema-ready via `users.id`, code change
  deferred).
- Session cleanup job for expired rows (`auth_sessions` rows linger until
  the next time that user logs in or a future cron lands).
