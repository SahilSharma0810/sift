# Sift — Development

## Prerequisites

- Docker Desktop (or Colima / OrbStack)
- Make
- An Anthropic API key (`ANTHROPIC_API_KEY`)

## First-time bootstrap

```bash
cp .env.example .env
# edit .env — at minimum set ANTHROPIC_API_KEY

make dev
```

`make dev` builds three images, brings up Postgres + backend + frontend,
waits for the DB to be healthy, then runs migrations. About 60 seconds the
first time; ~5 seconds on subsequent runs.

When it returns:
- **Frontend:** http://localhost:5173 — Vite dev server with HMR
- **Backend:** http://localhost:8000 — FastAPI with `--reload`
- **OpenAPI docs:** http://localhost:8000/docs
- **Postgres:** localhost:5432 — user `sift`, password `sift`, db `sift`

## Daily workflow

```bash
make up        # start
make down      # stop (keeps DB data + uploads)
make logs      # tail all services
make ps        # what's running
```

The source code is **bind-mounted** into the containers:
- `backend/app/**` → live `uvicorn --reload` on save
- `frontend/src/**` → Vite HMR

The `.venv` and `node_modules` live in **named docker volumes** so the
host's mac/linux binaries never collide with the container's.

## Migrations

```bash
make migrate                                    # apply pending
make migration name="add line items column"     # create a new one
```

After any change to `backend/app/db/models.py`, run `make migration` to
autogenerate and inspect the diff before applying.

## Tests

```bash
make test            # backend + frontend
make test-backend    # pytest only
make test-frontend   # vitest only
```

CI runs the same commands natively (no docker).

## Lint, format, types

```bash
make lint            # ruff check + import-linter + tsc --noEmit
make format          # ruff format + prettier
make types-gen       # regenerate frontend/src/types/generated/ from backend Pydantic
```

Per ADR-0005, the frontend TS types are **generated** from backend Pydantic
— never hand-edit anything under `frontend/src/types/generated/`. CI
verifies the file is fresh.

## Shells

```bash
make sh-backend     # bash inside backend container
make sh-frontend    # sh inside frontend container
make sh-db          # psql inside Postgres
```

## Nuking state

```bash
make nuke           # stop and delete all volumes (DB data + uploads + venvs)
```

Use when `pyproject.toml` or `package.json` changes in a way that the
named-volume venv/node_modules can't keep up with.

## Native (non-docker) dev

Docker is the supported primary path, but native works fine if you'd
rather. Install uv + Python 3.12 + Node 20 + pnpm + a local Postgres
(or point `DATABASE_URL` at a Neon branch per ADR-0002), then:

```bash
# Terminal 1 — backend
cd backend && uv sync --all-groups && uv run uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend && pnpm install && pnpm dev
```

## Deploying to Fly

Production lives in the root `Dockerfile` (multi-stage, single container,
SPA + API). Fly config is `fly.toml`.

```bash
fly launch                                              # first time
fly secrets set ANTHROPIC_API_KEY=...
fly secrets set DATABASE_URL=postgresql+psycopg://...   # Neon
fly deploy
```

`/health` is the deploy verification probe.
