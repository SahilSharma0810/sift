"""Search API — NL→SQL translate, structured search execution, export.

Thin handlers per ADR-0005. Translation lives in nl_translation_service;
SQL execution lives in search_service. The API never touches an LLM or
the DB directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.domain.models import InvoiceOut
from app.domain.nl_schema import StructuredQuery
from app.services.nl_translation_service import TranslationError, translate
from app.services.search_service import run_query

router = APIRouter()


class _TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=0, max_length=2000)


def _stringify_pydantic_errors(errors: list[dict]) -> list[dict]:
    """Pydantic errors carry exception objects in `ctx` which aren't JSON
    serializable. Coerce them to strings so the API response is clean.
    """
    out: list[dict] = []
    for err in errors:
        cleaned = dict(err)
        ctx = cleaned.get("ctx")
        if isinstance(ctx, dict):
            cleaned["ctx"] = {
                k: str(v) if isinstance(v, BaseException) else v for k, v in ctx.items()
            }
        out.append(cleaned)
    return out


@router.post("", response_model=list[InvoiceOut])
def run_search(
    query: StructuredQuery,
    session: Session = Depends(get_session),
) -> list[InvoiceOut]:
    """Execute a validated StructuredQuery against current extractions.

    The body is validated by FastAPI/Pydantic against `StructuredQuery`,
    so malformed clients receive a 422 with field-level errors automatically.
    The handler never sees a raw filter — only typed, whitelist-bounded
    FilterClauses.
    """
    return run_query(session, query=query)


@router.post("/translate", response_model=StructuredQuery)
def translate_nl(body: _TranslateRequest) -> StructuredQuery:
    """Translate a natural-language search string to a StructuredQuery.

    Returns a 422 with field-level errors if the LLM emitted a payload that
    doesn't validate — keeps the contract honest end-to-end (the UI never
    receives a broken query that would then 500 against /api/search).
    """
    try:
        return translate(natural_language=body.query)
    except TranslationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "raw_payload": exc.raw_payload,
                "errors": _stringify_pydantic_errors(exc.errors),
            },
        ) from exc
