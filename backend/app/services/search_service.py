"""Structured-query search execution.

Takes a validated StructuredQuery (already passed through the Pydantic
field-whitelist + per-field-op-compatibility gate) and runs it against
the database. The SQL is built clause-by-clause via SQLAlchemy expression
language — no raw SQL strings, no string interpolation of values. The
LLM never touches anything that ends up in a SQL statement; this service
only sees typed FilterClause objects.

Each clause is dispatched through a per-field handler that maps the
StructuredQuery semantics onto the columns:

  vendor_name    → vendors.name (joined)
  invoice_date   → extracted_fields->'invoice_date'->>'value' (parsed)
  total          → cast(extracted_fields->'total'->>'value' as numeric)
  subtotal       → cast(extracted_fields->'subtotal'->>'value' as numeric)
  tax_total      → cast(extracted_fields->'tax'->>'value' as numeric)
  currency       → extracted_fields->'currency'->>'value'
  triage_state   → extractions.predicted_triage_state
  review_status  → invoices.review_status
  has_anomaly    → EXISTS reason where type='anomaly'
  is_duplicate   → extractions.predicted_triage_state = 'likely_duplicate'
  raw_text       → extractions.raw_text_tsv @@ plainto_tsquery('english', ...)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import structlog
from sqlalchemy import and_, cast, func, select, text
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.expression import ColumnElement

from app.db.models import Extraction, Invoice, Vendor
from app.domain.models import InvoiceOut
from app.domain.nl_schema import FilterClause, StructuredQuery
from app.services.extraction_service import _orm_invoice_to_dto

log = structlog.get_logger(__name__)


# ---------- Per-field SQLAlchemy expression builders ----------


def _ef_value(field_name: str):
    """JSONB path: extracted_fields -> field_name ->> value (text)."""
    return Extraction.extracted_fields[field_name]["value"].astext


def _build_numeric_clause(field_json_key: str, op: str, value: Any) -> ColumnElement[bool]:
    """Cast the JSONB text value to NUMERIC for amount comparisons."""
    from sqlalchemy import Numeric

    casted = cast(_ef_value(field_json_key), Numeric)
    if op == "eq":
        return casted == value
    if op == "neq":
        return casted != value
    if op == "gt":
        return casted > value
    if op == "gte":
        return casted >= value
    if op == "lt":
        return casted < value
    if op == "lte":
        return casted <= value
    if op == "between":
        lo, hi = value
        return and_(casted >= lo, casted <= hi)
    raise ValueError(f"unsupported numeric op: {op}")


def _build_text_clause(json_key: str, op: str, value: Any) -> ColumnElement[bool]:
    col = _ef_value(json_key)
    if op == "eq":
        return col == value
    if op == "neq":
        return col != value
    if op == "in":
        return col.in_(value)
    if op == "contains":
        return col.ilike(f"%{value}%")
    raise ValueError(f"unsupported text op: {op}")


def _parse_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    raise ValueError(f"cannot parse date from {v!r}")


def _build_date_clause(json_key: str, op: str, value: Any) -> ColumnElement[bool]:
    """invoice_date is stored as a string per the extraction shape; we cast it
    to a Postgres date at query time. Invoices whose date string doesn't
    parse silently fall out of date-filtered queries — acceptable for now,
    flagged in EVAL.md if it becomes an issue."""

    col_text = _ef_value(json_key)
    casted = func.to_date(col_text, "YYYY-MM-DD")
    if op == "eq":
        return casted == _parse_date(value)
    if op == "neq":
        return casted != _parse_date(value)
    if op == "gt":
        return casted > _parse_date(value)
    if op == "gte":
        return casted >= _parse_date(value)
    if op == "lt":
        return casted < _parse_date(value)
    if op == "lte":
        return casted <= _parse_date(value)
    if op == "between":
        lo, hi = value
        return and_(casted >= _parse_date(lo), casted <= _parse_date(hi))
    raise ValueError(f"unsupported date op: {op}")


def _build_has_anomaly_clause(value: Any) -> ColumnElement[bool]:
    """Anomaly triage reason — JSONB contains check."""
    truthy = bool(value)
    expr = Extraction.predicted_triage_reasons.contains([{"type": "anomaly"}])
    return expr if truthy else ~expr


def _build_is_duplicate_clause(value: Any) -> ColumnElement[bool]:
    truthy = bool(value)
    if truthy:
        return Extraction.predicted_triage_state == "likely_duplicate"
    return Extraction.predicted_triage_state != "likely_duplicate"


def _build_raw_text_clause(op: str, value: Any) -> ColumnElement[bool]:
    """FTS via the generated tsvector column. `fts_matches` uses
    plainto_tsquery (safer — handles user-input phrasing); `contains`
    falls back to ILIKE for substring matching on the raw_text column."""
    if op == "fts_matches":
        return text("extractions.raw_text_tsv @@ plainto_tsquery('english', :q)").bindparams(
            q=str(value)
        )
    if op == "contains":
        return Extraction.raw_text.ilike(f"%{value}%")
    raise ValueError(f"unsupported raw_text op: {op}")


def _build_clause(clause: FilterClause) -> ColumnElement[bool]:
    f = clause.field
    op = clause.op
    v = clause.value

    if f == "vendor_name":
        if op in {"eq", "neq", "contains"}:
            target = v if not isinstance(v, list) else None
            if target is None:
                raise ValueError("vendor_name eq/neq/contains expects a scalar")
            if op == "eq":
                return Vendor.name == target
            if op == "neq":
                return Vendor.name != target
            return Vendor.name.ilike(f"%{target}%")
        if op == "in":
            return Vendor.name.in_(v if isinstance(v, list) else [v])

    if f == "invoice_date":
        return _build_date_clause("invoice_date", op, v)

    if f == "total":
        return _build_numeric_clause("total", op, v)
    if f == "subtotal":
        return _build_numeric_clause("subtotal", op, v)
    if f == "tax_total":
        return _build_numeric_clause("tax", op, v)

    if f == "currency":
        return _build_text_clause("currency", op, v)

    if f == "triage_state":
        if op == "eq":
            return Extraction.predicted_triage_state == v
        if op == "neq":
            return Extraction.predicted_triage_state != v
        if op == "in":
            return Extraction.predicted_triage_state.in_(v if isinstance(v, list) else [v])

    if f == "review_status":
        if op == "eq":
            return Invoice.review_status == v
        if op == "neq":
            return Invoice.review_status != v
        if op == "in":
            return Invoice.review_status.in_(v if isinstance(v, list) else [v])

    if f == "has_anomaly":
        return _build_has_anomaly_clause(v)
    if f == "is_duplicate":
        return _build_is_duplicate_clause(v)

    if f == "raw_text":
        return _build_raw_text_clause(op, v)

    raise ValueError(f"unsupported field/op combination: {f}/{op}")


def _sortable_column(name: str):
    if name == "vendor_name":
        return Vendor.name
    if name == "invoice_date":
        return func.to_date(_ef_value("invoice_date"), "YYYY-MM-DD")
    if name == "total":
        from sqlalchemy import Numeric

        return cast(_ef_value("total"), Numeric)
    if name == "subtotal":
        from sqlalchemy import Numeric

        return cast(_ef_value("subtotal"), Numeric)
    if name == "tax_total":
        from sqlalchemy import Numeric

        return cast(_ef_value("tax"), Numeric)
    raise ValueError(f"not a sortable column: {name}")


# ---------- Public API ----------


def run_query(session: Session, *, query: StructuredQuery) -> list[InvoiceOut]:
    """Execute a validated StructuredQuery and return matching InvoiceOut DTOs.

    Search runs against current extractions only. Returns the same
    InvoiceOut shape the inbox uses so the search UI can reuse the table
    component.
    """
    stmt = (
        select(Invoice)
        .join(Extraction, Extraction.invoice_id == Invoice.id)
        .join(Vendor, Vendor.id == Invoice.vendor_id, isouter=True)
        .where(Extraction.is_current.is_(True))
        .options(joinedload(Invoice.vendor))
    )

    where_clauses: list[ColumnElement[bool]] = []
    for clause in query.filters:
        where_clauses.append(_build_clause(clause))
    if where_clauses:
        stmt = stmt.where(and_(*where_clauses))

    # Sort
    if query.sort is not None:
        col = _sortable_column(query.sort[0])
        stmt = stmt.order_by(col.asc() if query.sort[1] == "asc" else col.desc())
    else:
        stmt = stmt.order_by(Invoice.uploaded_at.desc())

    stmt = stmt.limit(query.limit)

    log.info(
        "search.run_query",
        n_filters=len(query.filters),
        sort=query.sort,
        limit=query.limit,
    )

    rows = session.execute(stmt).unique().scalars().all()
    return [_orm_invoice_to_dto(inv, session) for inv in rows]
