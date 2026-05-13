"""Pure validators for extracted fields.

Each validator returns a typed result that the scorer consumes. No IO,
no LLM calls, no DB. The eval harness sits on this seam.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

# Rounding tolerance for amount validators — accommodates 1-2 cent OCR drift
# without permitting real reconciliation errors through.
AMOUNT_TOLERANCE = Decimal("0.02")


def math_reconciles(subtotal: float, tax: float, total: float) -> bool:
    """True if subtotal + tax ≈ total within AMOUNT_TOLERANCE.

    Uses Decimal internally to avoid IEEE 754 precision drift on OCR-sourced
    amounts (e.g. $1234.56, $19.99 — not exactly representable as floats).

    Rejects negative amounts (real invoices never have negative subtotals).
    """
    s = Decimal(str(subtotal))
    t = Decimal(str(tax))
    tt = Decimal(str(total))
    if s < 0 or t < 0 or tt < 0:
        return False
    return abs((s + t) - tt) <= AMOUNT_TOLERANCE


DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%B %d, %Y",
    "%d %B %Y",
)


# Common invoice currencies — covers >95% of in-scope cases. Not the full
# ISO 4217 set; not worth the dependency.
COMMON_CURRENCIES = frozenset(
    {
        "USD",
        "EUR",
        "GBP",
        "INR",
        "CAD",
        "AUD",
        "JPY",
        "CHF",
        "CNY",
        "SEK",
        "NOK",
        "DKK",
        "SGD",
        "HKD",
        "MXN",
        "BRL",
        "ZAR",
    }
)


def is_valid_currency_code(value: str | None) -> bool:
    """True if `value` looks like a valid ISO-style currency code."""
    if not value:
        return False
    return value.strip().upper() in COMMON_CURRENCIES


def is_valid_date(value: str | None) -> bool:
    """True if `value` parses as a date in any common invoice format.

    The validator does NOT pick a canonical format — that's the LLM's job and
    a per-vendor memory rule's job. This just answers: is the field
    structurally a date at all?
    """
    if not value:
        return False
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


# Required fields per the Day-1 happy-path extraction shape. Day-3 line-items
# and Day-4 tax_breakdown extend this list at their respective milestones.
REQUIRED_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "total",
    "currency",
)


def find_missing_required(fields: dict[str, object]) -> list[str]:
    """Names of required fields that are missing, None, or empty-string."""
    missing: list[str] = []
    for name in REQUIRED_FIELDS:
        value = fields.get(name)
        if value is None or value == "":
            missing.append(name)
    return missing
