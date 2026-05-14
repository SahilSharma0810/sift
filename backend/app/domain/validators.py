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


def tax_breakdown_sum_check(
    rows: list[dict] | tuple[dict, ...], header_tax: float | None
) -> tuple[bool, Decimal]:
    """Sum of per-jurisdiction `amount` values vs. the header `tax` field.

    Same shape as line_items_sum_check: returns (matches, delta). Used by
    the Day-4 service to log a warning when extracted breakdown rows
    don't reconcile against the extracted header tax. Does NOT change
    triage state in Day 4 — tax breakdown is quality-gated.
    """
    if not rows or header_tax is None:
        return (True, Decimal("0"))
    try:
        total: Decimal = Decimal("0")
        for row in rows:
            raw = row.get("amount", 0) or 0
            total += Decimal(str(raw))
    except (TypeError, ValueError, ArithmeticError):
        return (False, Decimal("0"))
    head = Decimal(str(header_tax))
    delta = total - head
    return (abs(delta) <= AMOUNT_TOLERANCE, delta)


def line_items_sum_check(
    line_items: list[dict] | tuple[dict, ...], subtotal: float | None
) -> tuple[bool, Decimal]:
    """Sum of line_total values vs. header subtotal, within AMOUNT_TOLERANCE.

    Returns (matches, delta). The Day-3 service logs this delta when it's
    nonzero but does NOT change triage state — line-item extraction is
    quality-gated and false-positive math mismatches would pollute the inbox.

    A None / empty line_items list returns (True, 0) — vacuously fine.
    """
    if not line_items or subtotal is None:
        return (True, Decimal("0"))
    try:
        total: Decimal = Decimal("0")
        for li in line_items:
            raw = li.get("line_total", 0) or 0
            total += Decimal(str(raw))
    except (TypeError, ValueError, ArithmeticError):
        return (False, Decimal("0"))
    sub = Decimal(str(subtotal))
    delta = total - sub
    return (abs(delta) <= AMOUNT_TOLERANCE, delta)


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


# Per ADR-0003: fields without a structural rule get a neutral 0.9 ceiling
# so history_score governs them. Math-failing amount fields drop to 0.2.
NEUTRAL_SCORE = 0.9
MATH_FAIL_FLOOR = 0.2
MISSING_OR_INVALID = 0.0
HIGH_SCORE = 1.0

AMOUNT_FIELDS = ("subtotal", "tax", "total")


def compute_structural_scores(fields: dict[str, object]) -> dict[str, float]:
    """Map each known field to a structural_score per ADR-0003.

    Returns a score per REQUIRED_FIELDS entry plus `subtotal` and `tax`.
    """
    scores: dict[str, float] = {}

    # Missing fields → 0.0
    missing = set(find_missing_required(fields))

    # Math reconciliation check — drives amount-field scores.
    math_ok = False
    try:
        math_ok = math_reconciles(
            subtotal=float(fields.get("subtotal", 0) or 0),
            tax=float(fields.get("tax", 0) or 0),
            total=float(fields.get("total", 0) or 0),
        )
    except (TypeError, ValueError):
        math_ok = False

    for field in AMOUNT_FIELDS:
        if field in missing:
            scores[field] = MISSING_OR_INVALID
        elif math_ok:
            scores[field] = HIGH_SCORE
        else:
            scores[field] = MATH_FAIL_FLOOR

    # Date — format-validate.
    if "invoice_date" in missing:
        scores["invoice_date"] = MISSING_OR_INVALID
    else:
        scores["invoice_date"] = (
            HIGH_SCORE if is_valid_date(str(fields.get("invoice_date"))) else MISSING_OR_INVALID
        )

    # Currency — code-validate.
    if "currency" in missing:
        scores["currency"] = MISSING_OR_INVALID
    else:
        scores["currency"] = (
            HIGH_SCORE
            if is_valid_currency_code(str(fields.get("currency")))
            else MISSING_OR_INVALID
        )

    # Fields without a structural rule (vendor_name, invoice_number) get the
    # neutral 0.9 ceiling per ADR-0003 unless missing.
    for field in ("vendor_name", "invoice_number"):
        scores[field] = MISSING_OR_INVALID if field in missing else NEUTRAL_SCORE

    return scores
