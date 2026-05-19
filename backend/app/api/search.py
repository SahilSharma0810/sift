"""Search API — NL→SQL translate, structured search execution, export.

Thin handlers per ADR-0005. Translation lives in nl_translation_service;
SQL execution lives in search_service. The API never touches an LLM or
the DB directly.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_clerk
from app.db.session import get_session
from app.domain.auth import ClerkOut
from app.domain.models import AggregateResult, InvoiceOut
from app.domain.nl_schema import StructuredQuery
from app.services.nl_translation_service import TranslationError, translate
from app.services.search_service import run_aggregate_query, run_query

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
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> list[InvoiceOut]:
    """Execute a validated StructuredQuery against current extractions.

    The body is validated by FastAPI/Pydantic against `StructuredQuery`,
    so malformed clients receive a 422 with field-level errors automatically.
    The handler never sees a raw filter — only typed, whitelist-bounded
    FilterClauses. If `aggregate` is set, this returns an empty list and
    the caller should hit /aggregate instead.
    """
    if query.aggregate is not None:
        return []
    return run_query(session, query=query)


@router.post("/aggregate", response_model=AggregateResult)
def run_aggregate(
    query: StructuredQuery,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> AggregateResult:
    """Execute a StructuredQuery whose `aggregate` directive is set,
    returning a count/sum/avg (optionally grouped). 422 if no aggregate
    was provided — the caller must opt in.
    """
    if query.aggregate is None:
        raise HTTPException(
            status_code=422,
            detail="query.aggregate is required for /aggregate endpoint",
        )
    return run_aggregate_query(session, query=query)

def _flatten_for_export(invoice: InvoiceOut) -> dict[str, str | float | None]:
    """One row per invoice, columns mirror the inbox UI."""
    ext = invoice.current_extraction
    fields = ext.extracted_fields if ext else {}

    def _v(name: str):
        f = fields.get(name) if fields else None
        return f.value if f else None

    return {
        "invoice_id": str(invoice.id),
        "vendor_name": _v("vendor_name"),
        "invoice_number": _v("invoice_number"),
        "invoice_date": _v("invoice_date"),
        "subtotal": _v("subtotal"),
        "tax": _v("tax"),
        "total": _v("total"),
        "currency": _v("currency"),
        "triage_state": ext.predicted_triage_state if ext else None,
        "review_status": invoice.review_status,
        "uploaded_at": invoice.uploaded_at.isoformat() if invoice.uploaded_at else None,
        "reasons": json.dumps([r.model_dump(mode="json") for r in ext.predicted_triage_reasons])
        if ext
        else "[]",
    }

@router.post("/export")
def export_search(
    query: StructuredQuery,
    format: Literal["csv", "json"] = Query(default="csv"),
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> Response:
    """Export the current search results as CSV or JSON.

    The structured query that produced the rows is serialized into the
    response payload itself (CSV: leading `#` comment lines; JSON: wrapper
    object) so the export is self-describing — a reviewer who finds the
    file later can see exactly what query produced it.
    """
    results = run_query(session, query=query)
    rows = [_flatten_for_export(inv) for inv in results]
    now = datetime.now(UTC).isoformat()
    query_json = query.model_dump_json()

    if format == "json":
        body = {
            "exported_at": now,
            "row_count": len(rows),
            "query": json.loads(query_json),
            "rows": rows,
        }
        return Response(
            content=json.dumps(body, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="sift-export-{now[:10]}.json"',
            },
        )

    buf = io.StringIO()

    buf.write(f"# Sift export · {now}\n")
    buf.write(f"# Rows: {len(rows)}\n")
    buf.write(f"# Query: {query_json}\n")

    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="sift-export-{now[:10]}.csv"',
        },
    )

@router.post("/translate", response_model=StructuredQuery)
def translate_nl(
    body: _TranslateRequest,
    _clerk: ClerkOut = Depends(get_current_clerk),
) -> StructuredQuery:
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
