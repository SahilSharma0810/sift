# syntax=docker/dockerfile:1.7-labs
#
# Sift — one Dockerfile, three stages.
#   1. frontend-build : Node + pnpm → static SPA bundle
#   2. python-build   : uv-resolved Python deps
#   3. runtime        : slim image; FastAPI serves API + SPA in one process
#

# ---------- 1) frontend-build ----------
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend

# Install pnpm via corepack (matches local dev).
RUN corepack enable && corepack prepare pnpm@9 --activate

COPY frontend/pnpm-lock.yaml frontend/package.json ./
RUN pnpm fetch
COPY frontend/ ./
RUN pnpm install --frozen-lockfile --offline
RUN pnpm build

# ---------- 2) python-build ----------
FROM python:3.12-slim-bookworm AS python-build
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app/backend

# uv for reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv

# System libs PyMuPDF + pdf2image need at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential poppler-utils \
 && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- 3) runtime ----------
FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SIFT_UPLOAD_DIR=/data/uploads

# Runtime libs: poppler-utils for pdf2image; libgl for PyMuPDF on some platforms.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /data/uploads

WORKDIR /app/backend
COPY --from=python-build /app/backend /app/backend
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Ensure entrypoint script is executable regardless of host file modes.
RUN chmod +x /app/backend/start.sh

EXPOSE 8000

# start.sh runs `alembic upgrade head` and then uvicorn on $PORT (default
# 8000). Same script works on Fly (PORT unset → 8000, matches fly.toml's
# internal_port) and Render (PORT set by the platform).
CMD ["/app/backend/start.sh"]
