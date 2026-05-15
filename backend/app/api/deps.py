from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.domain.auth import ClerkOut
from app.services.auth_service import resolve_session

SESSION_COOKIE_NAME = "sift_session"


def get_current_clerk(
    request: Request,
    session: Session = Depends(get_session),
) -> ClerkOut:
    signed = request.cookies.get(SESSION_COOKIE_NAME)
    clerk = resolve_session(session, signed, secret=get_settings().secret_key)
    if clerk is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return clerk
