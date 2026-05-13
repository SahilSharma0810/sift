"""Sift backend — vendor invoices to structured queryable data.

Layered architecture per ADR-0005:
    api/        thin route handlers
    services/   orchestration: imports from domain + adapters
    domain/     pure: no IO, no LLM, no DB
    adapters/   IO seams: llm_client, pdf_reader, storage repos

Dependency direction (enforced by import-linter):
    api → services → domain ← adapters
"""

__version__ = "0.1.0"
