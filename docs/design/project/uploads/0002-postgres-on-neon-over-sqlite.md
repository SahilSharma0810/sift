---
status: accepted
date: 2026-05-13
---

# Postgres (Neon free tier) over SQLite

## Context

Sift needs a database for invoice metadata, extracted JSON, full-text search,
duplicate detection, and per-vendor aggregate stats. The deployed demo
will hold ≤500 invoices; longer-term workloads are unknown.

## Decision

Use **managed Postgres on Neon's free tier** as the primary store. JSONB
column for extracted data with GIN indexes on commonly-queried paths;
`tsvector` for full-text search on raw OCR text; `pgvector` extension
enabled from day one (even if unused in v1) so semantic search is a
half-day add later, not a DB migration.

SQLAlchemy 2.0 (sync) as the ORM. Alembic for migrations. Local dev via
`docker compose` or a Neon branch.

## Considered Options

- **SQLite + FTS5.** Functionally fine at this scale. Rejected because:
  - JSON path queries (`extracted_data->'tax_breakdown'->>'jurisdiction'`)
    require re-parsing per row in SQLite; JSONB+GIN in Postgres indexes
    them properly. The depth-bet features (per-jurisdiction tax queries,
    per-vendor anomaly aggregates) lean on this.
  - Vector search future-proofing: `sqlite-vec` works but `pgvector` is
    production-tested; adding semantic search on Day 5 becomes a half-day
    task vs a DB swap.
  - "Production signal" matters for the Zamp evaluation context — Zamp
    operates at finance-grade production scale.
- **Postgres self-hosted (Fly Postgres app or docker).** More moving parts
  than the managed option, no real upside for a demo.
- **DuckDB.** Excellent for the analytical-query slice (vendor history,
  spending over time) but weaker as the transactional primary store.
- **Supabase free tier.** Comparable to Neon; picked Neon for the
  branch-database workflow and lower cold-start latency in 2026.

## Consequences

- One extra service to manage at deploy time (Neon project + connection
  string in Fly secrets). Tradeoff accepted.
- ~5-50ms query latency over the network instead of zero-latency in-process
  SQLite reads. Negligible at our QPS.
- Local dev needs a Postgres instance (`docker compose up`) instead of a
  file. One-time setup, then identical to SQLite for the rest of the build.
- Schema design uses JSONB + tsvector + vector types — no longer trivially
  portable to SQLite. The substitution would be straightforward if ever
  needed.
- `pgvector` is enabled from day one but only used if Day 5 stretch
  includes semantic search. Zero cost to leave dormant.
