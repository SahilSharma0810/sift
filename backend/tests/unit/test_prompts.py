"""Prompt loader smoke tests — verifies versioned file + hash + cache."""

from __future__ import annotations

from app.prompts import load


def test_extraction_header_v1_loads() -> None:
    p = load("extraction_header_v1")
    assert p.name == "extraction_header_v1"
    assert "vendor invoices" in p.body.lower()
    assert p.schema["name"] == "extract_invoice_header"
    assert len(p.body_hash) == 16
    assert len(p.schema_hash) == 16


def test_load_is_cached() -> None:
    a = load("extraction_header_v1")
    b = load("extraction_header_v1")
    assert a is b  # same cached object


def test_schema_required_fields_match_extraction_contract() -> None:
    """The schema's `required` list drives REQUIRED_FIELDS guarantees downstream."""
    p = load("extraction_header_v1")
    required = set(p.schema["input_schema"]["required"])
    # Day-1 header fields must all be required at the schema level.
    assert {
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "subtotal",
        "tax",
        "total",
        "currency",
    } == required
