"""API spend tracking — read-only dashboard endpoint.

Returns the current spend, the configured cap, and a few derived fields
so the frontend doesn't recompute percent_used / remaining client-side.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_clerk
from app.config import get_settings
from app.db.session import get_session
from app.domain.auth import ClerkOut
from app.services import usage_service

router = APIRouter()


class UsageOut(BaseModel):
    spent_usd: float
    limit_usd: float
    remaining_usd: float
    percent_used: float
    call_count: int
    exhausted: bool


@router.get("", response_model=UsageOut)
def read_usage(
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> UsageOut:
    settings = get_settings()
    summary = usage_service.get_summary(session, limit_usd=settings.api_budget_usd)
    return UsageOut(
        spent_usd=round(summary.spent_usd, 4),
        limit_usd=summary.limit_usd,
        remaining_usd=round(summary.remaining_usd, 4),
        percent_used=round(summary.percent_used, 4),
        call_count=summary.call_count,
        exhausted=summary.exhausted,
    )
