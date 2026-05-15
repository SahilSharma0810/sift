# DEPLOY.md

Sift ships as a single Docker image that serves the FastAPI API and the
Vite SPA on one port. Postgres lives on Neon (managed) per ADR-0002.

Target: **Render** (free tier) — see `render.yaml`. Cold-start after
15 min idle; no persistent disk on the free plan, so uploads reset on
every restart.

## Render (free tier)

1. Sign up at <https://dashboard.render.com>.
2. **New → Blueprint** → connect this GitHub repo. Render reads
   `render.yaml` and provisions a single web service named `sift`.
3. Provision Postgres on [Neon](https://neon.tech) — free tier is fine.
   Convert the connection string from `postgres://…` to
   `postgresql+psycopg://…?sslmode=require` (SQLAlchemy 2.0 sync per
   ADR-0002).
4. In the Render dashboard, set the two secret env vars on the service:
   - `DATABASE_URL` — the Neon URL from step 3.
   - `SIFT_SECRET_KEY` — `openssl rand -hex 32`.
5. Click **Apply**. First deploy runs `alembic upgrade head` and then
   uvicorn (per `dockerCommand` in `render.yaml`).
6. The live URL is `https://sift.onrender.com` (or whatever name Render
   picked; the dashboard shows it).

Every push to `main` triggers an auto-deploy by default. To deploy a
non-main branch, change the branch on the service in the dashboard.

### Anthropic mode on Render

By default `render.yaml` sets `SIFT_LLM_PROVIDER=stub` so the live URL
costs nothing per request. To run the deploy in anthropic mode, set
these as **secret** env vars in the Render dashboard (not in the YAML):

```
SIFT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

There is no per-request token-budget cap; reviewers running the live URL
in anthropic mode burn credits proportional to upload activity. The
stub-mode default protects against this.

## What the container does on boot

The `Dockerfile` at repo root produces a multi-stage image: stage 1
builds the Vite SPA, stage 2 installs Python deps via `uv sync --no-dev`,
stage 3 copies the SPA into `/app/frontend/dist` so FastAPI's
`StaticFiles` mount picks it up.

`backend/start.sh` then runs:

1. `alembic upgrade head` — applies any pending migrations.
2. `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — Render sets
   `PORT`; locally it defaults to 8000.

If migrations fail, the deploy aborts before the new container becomes
healthy.

## Migration safety

`alembic upgrade head` runs on every deploy. Migrations are sequenced
and backward-compatible per ADR-0002 — each migration adds
columns/tables without dropping existing data, and the corresponding
code change tolerates older rows (server-defaults backfill new
columns). Rolling back a deploy without rolling back the migration is
safe.

If a migration needs to be destructive (rare, never done so far),
document it in the migration file + tag the release.

## Local production-mode test

The same Dockerfile can be exercised locally to catch deploy bugs
before they hit Render:

```bash
docker build -t sift-prod .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL='postgresql+psycopg://sift:sift@host.docker.internal:5432/sift' \
  -e SIFT_LLM_PROVIDER=stub \
  -v "$(pwd)/uploads:/data/uploads" \
  sift-prod
```

If this serves `http://localhost:8000` correctly (UI loads, drop a
PDF, see the demo flow), the Render deploy will succeed too.

## Auth — required secrets

The login backend needs `SIFT_SECRET_KEY` (covered in the Render setup
above) and a demo user. The demo user is seeded automatically by
`make demo` (using `SIFT_DEMO_EMAIL` / `SIFT_DEMO_PASSWORD`). If you
want a different demo email or password in prod, set those env vars on
the service before running the seed:

```
SIFT_DEMO_EMAIL=...
SIFT_DEMO_PASSWORD=...
```

The seed function is idempotent — re-running `make demo` will not reset
an existing demo user's password.

`SIFT_COOKIE_SECURE=true` is set in `render.yaml` so session cookies
are HTTPS-only in production.
