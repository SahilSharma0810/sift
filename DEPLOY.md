# DEPLOY.md

Sift deploys as a single Docker image to Fly.io with Postgres on Neon.

## One-time setup

### 1. Provision Postgres (Neon)

Create a free-tier project at [neon.tech](https://neon.tech). Take the pooled connection string from the dashboard and convert it to SQLAlchemy form:

```
postgres://user:pass@ep-xxx.region.aws.neon.tech/sift?sslmode=require
   →
postgresql+psycopg://user:pass@ep-xxx.region.aws.neon.tech/sift?sslmode=require
```

The `+psycopg` driver is required because Sift uses SQLAlchemy 2.0 sync (ADR-0002).

### 2. Provision Fly app

```bash
flyctl auth login
flyctl apps create sift   # or any unique name (update fly.toml accordingly)
flyctl volumes create sift_uploads --region iad --size 1
```

### 3. Set secrets

```bash
flyctl secrets set DATABASE_URL='postgresql+psycopg://user:pass@.../sift?sslmode=require'

# Optional — only if you want the live deploy to use the real Anthropic provider.
# Skip these for a stub-mode deploy that's safe to leave running.
flyctl secrets set SIFT_LLM_PROVIDER=anthropic
flyctl secrets set ANTHROPIC_API_KEY=sk-ant-...
```

`SIFT_LLM_PROVIDER` defaults to `stub` if unset — every LLM call goes through `StubLLMClient` and the live URL costs nothing per request. This is the recommended setting for a shared review URL.

### 4. (Optional) Wire GitHub Actions auto-deploy

```bash
flyctl auth token | gh secret set FLY_API_TOKEN
```

`.github/workflows/deploy.yml` then deploys on every push to `main`.

## Deploying

### One-shot manual deploy

```bash
flyctl deploy
```

The `Dockerfile` at repo root produces a multi-stage image: stage 1 builds the Vite SPA, stage 2 installs Python deps via `uv sync --no-dev`, stage 3 copies the SPA into `/app/frontend/dist` so FastAPI's `StaticFiles` mount picks it up. The `fly.toml` mounts a volume at `/data` for invoice uploads.

The container runs:
1. `alembic upgrade head` — applies any pending migrations
2. `uvicorn app.main:app --host 0.0.0.0 --port 8000`

If migrations fail, the deploy aborts before the new container becomes healthy.

### Migration safety

`alembic upgrade head` runs on every deploy. Migrations are sequenced and backward-compatible per ADR-0002 — each migration adds columns/tables without dropping existing data, and the corresponding code change tolerates older rows (server-defaults backfill new columns). Rolling back a deploy without rolling back the migration is safe.

If a migration needs to be destructive (rare, never done so far), document it in the migration file + tag the release.

## Live-URL placeholder

This section will carry the canonical `https://sift.fly.dev` URL once the first deploy lands.

## Local production-mode test

The same Dockerfile can be exercised locally to catch deploy bugs before they hit Fly:

```bash
docker build -t sift-prod .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL='postgresql+psycopg://sift:sift@host.docker.internal:5432/sift' \
  -e SIFT_LLM_PROVIDER=stub \
  -v "$(pwd)/uploads:/data/uploads" \
  sift-prod
```

If this serves `http://localhost:8000` correctly (UI loads, drop a PDF, see the demo flow), the Fly deploy will succeed too.

## Cost ceiling

In stub mode the Fly app is ~$2-5/month idle (single shared-cpu-1x VM, auto-stop after 5 min idle, free Neon tier). In anthropic mode, plus whatever Claude API spend the demo gets.

There is no per-request token-budget cap; reviewers running the live URL in anthropic mode will burn credits proportional to upload activity. The stub-mode default protects against this.

## Rollback

```bash
flyctl releases list
flyctl deploy --image-label v<N>
```

Or via the Fly dashboard. Rolling back the image without rolling back migrations is safe as long as migrations remain additive.
