"""Pure validators for extracted fields.

Each validator returns a typed result that the scorer consumes. No IO,
no LLM calls, no DB. The eval harness sits on this seam.
"""

from __future__ import annotations

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
