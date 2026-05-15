"""Parse free-form invoice date strings into canonical (iso_from, iso_to).

Decoupled from the LLM: the model emits `value` verbatim (as instructed by
the extraction prompt), Python normalises to ISO endpoints here. The
search SQL filters on `iso_from`. Backfill and live extraction both go
through this one function so the canonical form can never drift between
new rows and old rows.

Point dates set `iso_from == iso_to`. Billing periods ("9/21/20 - 9/26/20")
set them to the range endpoints. Month-only dates ("October 2020") fan
out to the first/last day of the month. Unparseable strings return
(None, None) — same effect as today (excluded from date filters), but
now honestly modeled instead of silently failing a SQL cast.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

_RANGE_SEPARATORS = (" - ", " – ", " — ", " to ", " through ")

_FORMATS_DAY: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%B-%Y",
    "%b %d, %y",
    "%d-%b-%y",
)

_FORMATS_MONTH_ONLY: tuple[str, ...] = (
    "%B %Y",
    "%b %Y",
    "%b-%Y",
    "%B-%Y",
    "%b-%y",
    "%B-%y",
)


def _try_parse(text: str) -> tuple[date | None, bool]:
    """Return (date, is_month_only). For month-only, day is set to 1."""
    for fmt in _FORMATS_DAY:
        try:
            return (datetime.strptime(text, fmt).date(), False)
        except ValueError:
            continue
    for fmt in _FORMATS_MONTH_ONLY:
        try:
            return (datetime.strptime(text, fmt).date().replace(day=1), True)
        except ValueError:
            continue
    return (None, False)


def _to_endpoints(d: date, month_only: bool) -> tuple[str, str]:
    if month_only:
        last = monthrange(d.year, d.month)[1]
        return (d.replace(day=1).isoformat(), d.replace(day=last).isoformat())
    return (d.isoformat(), d.isoformat())


def parse_date_or_range(text: str | None) -> tuple[str | None, str | None]:
    """Best-effort parse of a verbatim date string into (iso_from, iso_to)."""
    if not text:
        return (None, None)
    s = str(text).strip()
    if not s:
        return (None, None)

    for sep in _RANGE_SEPARATORS:
        if sep in s:
            left, right = s.split(sep, 1)
            d_left, ml_left = _try_parse(left.strip())
            d_right, ml_right = _try_parse(right.strip())
            if d_left is None or d_right is None:
                return (None, None)
            iso_from, _ = _to_endpoints(d_left, ml_left)
            _, iso_to = _to_endpoints(d_right, ml_right)
            return (iso_from, iso_to)

    parsed, is_month = _try_parse(s)
    if parsed is None:
        return (None, None)
    return _to_endpoints(parsed, is_month)
