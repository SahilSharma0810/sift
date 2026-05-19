"""NL → StructuredQuery schema per ADR-0004.

Pure domain types. The translator service (services/nl_translation_service.py)
calls Claude tool-use to produce one of these; the validator here is the
hard contract — malformed outputs are rejected before any SQL is built.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

SortableField = Literal[
    "vendor_name",
    "invoice_date",
    "total",
    "subtotal",
    "tax_total",
]

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

class FilterClause(BaseModel):
    """One filter clause — implicit AND between clauses in a StructuredQuery.

    Per-field op compatibility is enforced — see ADR-0004.
    """

    model_config = ConfigDict(extra="forbid")

    field: QueryField
    op: QueryOp

    value: str | float | int | bool | date | list[str] | list[float] | list[int] | tuple[date, date]

    @model_validator(mode="after")
    def _check_op_compat(self) -> FilterClause:
        allowed = FIELD_OP_COMPATIBILITY.get(self.field, set())
        if self.op not in allowed:
            raise ValueError(
                f"op '{self.op}' is not allowed on field '{self.field}'. Allowed: {sorted(allowed)}"
            )
        return self

GroupableField = Literal[
    "vendor_name",
    "triage_state",
    "review_status",
    "currency",
]

AggregateField = Literal[
    "total",
    "subtotal",
    "tax_total",
]

AggregateOp = Literal["count", "sum", "avg"]


class Aggregate(BaseModel):
    """Aggregation directive — count/sum/avg, optionally grouped.

    - `op="count"` ignores `field` (counts rows matching `filters`).
    - `op="sum"` / `op="avg"` require `field` (one of the numeric columns).
    - `group_by` is optional. When set, the result is a list of
      `{group, value}` rows sorted by `value` desc.
    - `limit` on the parent StructuredQuery caps grouped output rows.
    """

    model_config = ConfigDict(extra="forbid")

    op: AggregateOp
    field: AggregateField | None = None
    group_by: GroupableField | None = None

    @model_validator(mode="after")
    def _check_field_op_compat(self) -> Aggregate:
        if self.op == "count":
            if self.field is not None:
                raise ValueError("count does not take a `field` (it counts rows).")
            return self
        if self.field is None:
            raise ValueError(f"op '{self.op}' requires a numeric `field`.")
        return self


class StructuredQuery(BaseModel):
    """Flat conjunction (implicit AND) + sort + limit + untranslated_intent
    + optional aggregate. Per ADR-0004 (extended for aggregation v2).

    No OR/NOT/nested groups — the chip UI is still a flat row. When
    `aggregate` is set, the result shape switches from invoice rows to
    aggregate rows; the frontend dispatches on this.
    """

    model_config = ConfigDict(extra="forbid")

    filters: list[FilterClause] = Field(default_factory=list)
    sort: tuple[SortableField, Literal["asc", "desc"]] | None = None
    limit: int = Field(default=50, ge=1, le=500)
    untranslated_intent: str | None = None
    aggregate: Aggregate | None = None
