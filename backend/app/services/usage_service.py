"""API spend tracking — single seam for the $5 LLM budget cap.

The LLMClient wrapper in adapters/llm_client.py calls into this module
before every billable call (to check the cap) and after every billable
call (to record the cost). The /api/usage route also reads through here
to render the dashboard widget.

Usage rows are written in their own short transaction so a recorded LLM
call is never lost to a rollback in the calling request — every dollar
spent is audited even if the surrounding pipeline aborts.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ApiUsage
from app.services.pricing import cost_usd_for_usage

log = structlog.get_logger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised before an LLM call when the current spend has reached the cap.

    Carries the numbers needed by the API layer to render a useful 402.
    """

    def __init__(self, *, spent_usd: float, limit_usd: float) -> None:
        self.spent_usd = spent_usd
        self.limit_usd = limit_usd
        super().__init__(
            f"API spend cap reached: ${spent_usd:.4f} of ${limit_usd:.2f} used"
        )


@dataclass(frozen=True, slots=True)
class UsageSummary:
    spent_usd: float
    limit_usd: float
    call_count: int

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)

    @property
    def percent_used(self) -> float:
        if self.limit_usd <= 0:
            return 0.0
        return min(1.0, self.spent_usd / self.limit_usd)

    @property
    def exhausted(self) -> bool:
        return self.spent_usd >= self.limit_usd


def total_cost_usd(session: Session) -> float:
    """Sum of all recorded LLM costs in USD."""
    value = session.execute(select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0))).scalar_one()
    return float(value or 0.0)


def call_count(session: Session) -> int:
    value = session.execute(select(func.count(ApiUsage.id))).scalar_one()
    return int(value or 0)


def get_summary(session: Session, *, limit_usd: float) -> UsageSummary:
    return UsageSummary(
        spent_usd=total_cost_usd(session),
        limit_usd=limit_usd,
        call_count=call_count(session),
    )


def assert_within_budget(session: Session, *, limit_usd: float) -> None:
    """Raise BudgetExceededError if spending has already reached the cap.

    The check is intentionally coarse — at-cap is at-cap, no soft grace.
    Concurrent callers can race past the line by the cost of one call;
    we accept that over fine-grained locking on a $5 cap.
    """
    spent = total_cost_usd(session)
    if spent >= limit_usd:
        raise BudgetExceededError(spent_usd=spent, limit_usd=limit_usd)


def record_usage(
    session_factory: sessionmaker[Session],
    *,
    model: str,
    spec_name: str,
    usage: dict[str, int],
) -> float:
    """Persist a single LLM call's usage and return the computed USD cost.

    Opens its own session so the audit row commits independently of the
    surrounding request transaction. Failures here are logged but never
    propagate — losing visibility into a cost row is worse than letting
    the user see a successful response.
    """
    cost = cost_usd_for_usage(model=model, usage=usage)
    try:
        with session_factory() as session:
            row = ApiUsage(
                model=model,
                spec_name=spec_name,
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                cache_creation_input_tokens=int(
                    usage.get("cache_creation_input_tokens", 0) or 0
                ),
                cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                cost_usd=cost,
            )
            session.add(row)
            session.commit()
    except Exception as exc:
        log.warning(
            "api_usage.record_failed",
            error=str(exc),
            model=model,
            spec_name=spec_name,
        )
    return cost
