"""Domain layer — pure logic.

NO imports from app.services, app.adapters, app.api, app.db.
NO IO, no LLM calls, no DB. Pydantic models, validators, scoring, triage,
cascade, anomalies, duplicates, NL schema.

Enforced by import-linter (see pyproject.toml).
"""
