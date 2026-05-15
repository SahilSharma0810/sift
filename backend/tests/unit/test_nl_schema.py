"""Tests for NL → StructuredQuery schema per ADR-0004.

The validator is the safety contract. If these pass, malformed LLM outputs
cannot reach the SQL builder.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.nl_schema import FilterClause, StructuredQuery

class TestFilterClause:
    def test_basic_eq(self) -> None:
        f = FilterClause(field="vendor_name", op="eq", value="Vega Logistics")
        assert f.value == "Vega Logistics"

    def test_numeric_gt(self) -> None:
        f = FilterClause(field="total", op="gt", value=5000)
        assert f.value == 5000

    def test_op_field_incompat_rejected(self) -> None:

        with pytest.raises(ValidationError):
            FilterClause(field="vendor_name", op="gt", value="x")

    def test_fts_only_on_raw_text(self) -> None:

        with pytest.raises(ValidationError):
            FilterClause(field="total", op="fts_matches", value="anything")
        f = FilterClause(field="raw_text", op="fts_matches", value="vega")
        assert f.field == "raw_text"

    def test_off_whitelist_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FilterClause(field="rogue_field", op="eq", value="x")  # type: ignore[arg-type]

class TestStructuredQuery:
    def test_minimal(self) -> None:
        q = StructuredQuery()
        assert q.filters == []
        assert q.limit == 50

    def test_realistic_vega_query(self) -> None:
        """`vega last 3 months over $5k` should round-trip cleanly."""
        q = StructuredQuery(
            filters=[
                FilterClause(field="vendor_name", op="eq", value="Vega Logistics"),
                FilterClause(field="invoice_date", op="gte", value=date(2026, 2, 13)),
                FilterClause(field="total", op="gt", value=5000),
            ],
            sort=("invoice_date", "desc"),
            limit=50,
        )
        assert len(q.filters) == 3
        assert q.sort == ("invoice_date", "desc")

    def test_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            StructuredQuery(limit=0)
        with pytest.raises(ValidationError):
            StructuredQuery(limit=10_000)

    def test_untranslated_intent_preserves_partial(self) -> None:
        """ADR-0004: best-effort partial translation. Dropped phrase is surfaced."""
        q = StructuredQuery(
            filters=[FilterClause(field="vendor_name", op="eq", value="Vega")],
            untranslated_intent="higher than median",
        )
        assert q.untranslated_intent == "higher than median"
