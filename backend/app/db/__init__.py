"""Database — SQLAlchemy ORM models, session factory, alembic.

ORM models live here as a thin storage projection. The domain layer's
Pydantic models are the source of truth for business types; SQLAlchemy
models map them to Postgres.
"""
