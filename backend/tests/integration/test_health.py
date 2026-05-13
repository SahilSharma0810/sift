"""Smoke test on /health — proves the FastAPI app boots."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_responds_ok() -> None:
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body
