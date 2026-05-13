# Sift — developer convenience commands.
#
# Docker is the primary dev path. Native dev (uv + pnpm directly) still
# works for anyone who prefers it; just point DATABASE_URL at a local
# Postgres or a Neon branch.

.DEFAULT_GOAL := help
.PHONY: help dev up down restart logs ps build migrate migration revision \
        test test-backend test-frontend lint format types-gen \
        sh-backend sh-frontend sh-db clean nuke

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------- one-shot bootstrap ----------
dev: up wait-db migrate ## Bring up the stack and run migrations (first-time bootstrap).
	@echo "✓ Sift is up.  backend: http://localhost:8000  frontend: http://localhost:5173"

# ---------- compose lifecycle ----------
up: ## Start all services (db, backend, frontend).
	docker compose up -d --build

down: ## Stop all services (keep volumes).
	docker compose down

restart: ## Restart all services.
	docker compose restart

build: ## Rebuild images without starting.
	docker compose build

ps: ## List running services.
	docker compose ps

logs: ## Tail logs from all services.
	docker compose logs -f --tail=100

wait-db: ## Block until Postgres is ready.
	@echo "Waiting for Postgres to be healthy..."
	@until docker compose exec -T db pg_isready -U sift -d sift > /dev/null 2>&1; do sleep 1; done
	@echo "✓ Postgres ready"

# ---------- migrations ----------
migrate: ## Run pending alembic migrations.
	docker compose exec backend uv run alembic upgrade head

migration: ## Create a new migration. Usage: make migration name="add foo table"
	@if [ -z "$(name)" ]; then echo "Usage: make migration name=\"description\""; exit 1; fi
	docker compose exec backend uv run alembic revision --autogenerate -m "$(name)"

revision: migration ## Alias for `migration`.

# ---------- tests + lint ----------
test: test-backend test-frontend ## Run all tests.

test-backend: ## Run pytest inside the backend container.
	docker compose exec backend uv run pytest -q

test-frontend: ## Run vitest inside the frontend container.
	docker compose exec frontend pnpm vitest run

lint: ## Lint + type-check both stacks.
	docker compose exec backend uv run ruff check .
	docker compose exec backend uv run lint-imports
	docker compose exec frontend pnpm tsc --noEmit

format: ## Format code in both stacks.
	docker compose exec backend uv run ruff format .
	docker compose exec frontend pnpm prettier --write src

types-gen: ## Regenerate frontend TS types from backend Pydantic.
	docker compose exec backend uv run python /app/../scripts/generate_types.py

# ---------- shells ----------
sh-backend: ## Open a shell in the backend container.
	docker compose exec backend bash

sh-frontend: ## Open a shell in the frontend container.
	docker compose exec frontend sh

sh-db: ## Open a psql shell in the database container.
	docker compose exec db psql -U sift -d sift

# ---------- cleanup ----------
clean: ## Stop and remove containers (keep volumes).
	docker compose down --remove-orphans

nuke: ## Stop everything AND delete volumes (will lose all DB data + uploads).
	docker compose down -v --remove-orphans
