"""NL → StructuredQuery schema per ADR-0004.

Pure domain types. The translator service (services/nl_translation_service.py)
calls Claude tool-use to produce one of these; the validator here is the
hard contract — malformed outputs are rejected before any SQL is built.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------- Whitelisted fields ----------
QueryField = Literal[
    "vendor_name",
    "invoice_date",
    "total",
    "subtotal",
    "tax_total",
    "currency",
    "triage_state",
    "review_status",
    "has_anomaly",
    "is_duplicate",
    "raw_text",
]

# Subset that's sortable.
SortableField = Literal[
    "vendor_name",
    "invoice_date",
    "total",
    "subtotal",
    "tax_total",
]

# ---------- Operators ----------
QueryOp = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "between",
    "contains",
    "fts_matches",
]

# Per-field op compatibility — ADR-0004. Validator enforces this.
FIELD_OP_COMPATIBILITY: dict[QueryField, set[str]] = {
    "vendor_name": {"eq", "neq", "in", "contains"},
    "invoice_date": {"eq", "neq", "gt", "gte", "lt", "lte", "between"},
    "total": {"eq", "neq", "gt", "gte", "lt", "lte", "between"},
    "subtotal": {"eq", "neq", "gt", "gte", "lt", "lte", "between"},
    "tax_total": {"eq", "neq", "gt", "gte", "lt", "lte", "between"},
    "currency": {"eq", "neq", "in"},
    "triage_state": {"eq", "neq", "in"},
    "review_status": {"eq", "neq", "in"},
    "has_anomaly": {"eq"},
    "is_duplicate": {"eq"},
    "raw_text": {"contains", "fts_matches"},
}


# ---------- FilterClause + StructuredQuery ----------
class FilterClause(BaseModel):
    """One filter clause — implicit AND between clauses in a StructuredQuery.

    Per-field op compatibility is enforced — see ADR-0004.
    """

    model_config = ConfigDict(extra="forbid")

    field: QueryField
    op: QueryOp
    value: str | float | int | bool | date | list[str] | tuple[date, date]

    @model_validator(mode="after")
    def _check_op_compat(self) -> FilterClause:
        allowed = FIELD_OP_COMPATIBILITY.get(self.field, set())
        if self.op not in allowed:
            raise ValueError(
                f"op '{self.op}' is not allowed on field '{self.field}'. Allowed: {sorted(allowed)}"
            )
        return self


class StructuredQuery(BaseModel):
    """Flat conjunction (implicit AND) + sort + limit + untranslated_intent.

    Per ADR-0004. No OR/NOT/nested groups in v1 — the chip UI is a flat row.
    """

    model_config = ConfigDict(extra="forbid")

    filters: list[FilterClause] = Field(default_factory=list)
    sort: tuple[SortableField, Literal["asc", "desc"]] | None = None
    limit: int = Field(default=50, ge=1, le=500)
    untranslated_intent: str | None = None
