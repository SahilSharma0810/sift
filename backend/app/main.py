"""FastAPI entry — mounts routers, configures CORS, sets up structured logging.

This file stays small. Real work lives in api/, services/, domain/, adapters/.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings

def configure_logging(level: str, fmt: str) -> None:
    """Structured JSON logging to stdout — per PLAN.md pre-grilled non-decision."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    if settings.using_dev_secret:
        structlog.get_logger().warning(
            "auth.dev_secret_in_use",
            hint="set SIFT_SECRET_KEY in production",
        )

    app = FastAPI(
        title="Sift",
        version=__version__,
        description="Vendor invoices → structured queryable data",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe — used by Render's health check for deploy verification."""
        return {"status": "ok", "version": __version__}

    @app.get("/api/meta")
    def meta() -> dict[str, str]:
        """Surface non-secret runtime config so the UI can show a stub-mode pill."""
        return {"version": __version__, "llm_provider": settings.llm_provider}

    from app.api import anomalies, auth, invoices, search

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(anomalies.router, prefix="/api/anomalies", tags=["anomalies"])

    spa_dist = Path("/app/frontend/dist")
    if spa_dist.exists():
        app.mount("/assets", StaticFiles(directory=spa_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa_fallback(path: str) -> FileResponse:
            """Serve index.html for any unknown path — React Router handles routing."""
            return FileResponse(spa_dist / "index.html")

    return app

app = create_app()
