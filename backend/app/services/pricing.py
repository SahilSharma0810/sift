"""Anthropic per-model pricing (USD) and cost computation for a usage payload.

Prices are USD per million tokens, matched on tier substring (haiku / sonnet /
opus) so a config change that pins a specific date-stamped model still
resolves to the right tier. Cache-write tokens cost 1.25x the input rate,
cache-read tokens cost 0.1x — Anthropic's standard prompt-caching schedule.

Update the constants here when pricing changes; the rest of the system reads
through `cost_usd_for_usage`.
"""

from __future__ import annotations

from typing import TypedDict

class _TierPrice(TypedDict):
    input_per_mtok: float
    output_per_mtok: float

_TIER_PRICES: dict[str, _TierPrice] = {
    "haiku": {"input_per_mtok": 1.00, "output_per_mtok": 5.00},
    "sonnet": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "opus": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
}

_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10

def _tier_for_model(model: str) -> str | None:
    lower = model.lower()
    for tier in _TIER_PRICES:
        if tier in lower:
            return tier
    return None

def cost_usd_for_usage(*, model: str, usage: dict[str, int]) -> float:
    """Compute the USD cost for a single LLM call.

    Returns 0.0 for unknown models — the stub provider and any future
    non-billed seam (mocks, fixtures) shouldn't accidentally accrue cost
    against the budget. Real billing surfaces in the audit row regardless.
    """
    tier = _tier_for_model(model)
    if tier is None:
        return 0.0
    price = _TIER_PRICES[tier]
    input_rate = price["input_per_mtok"] / 1_000_000
    output_rate = price["output_per_mtok"] / 1_000_000

    base_input = float(usage.get("input_tokens", 0) or 0) * input_rate
    output = float(usage.get("output_tokens", 0) or 0) * output_rate
    cache_write = (
        float(usage.get("cache_creation_input_tokens", 0) or 0)
        * input_rate
        * _CACHE_WRITE_MULTIPLIER
    )
    cache_read = (
        float(usage.get("cache_read_input_tokens", 0) or 0)
        * input_rate
        * _CACHE_READ_MULTIPLIER
    )
    return base_input + output + cache_write + cache_read
