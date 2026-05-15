from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME, get_current_clerk
from app.config import get_settings
from app.db.session import get_session
from app.domain.auth import ClerkOut, LoginIn
from app.services.auth_service import login as login_service, logout as logout_service

router = APIRouter()


class LoginResponse(BaseModel):
    user: ClerkOut


@router.post("/login", response_model=LoginResponse)
def login_endpoint(
    body: LoginIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    settings = get_settings()
    outcome = login_service(
        session,
        email=body.email,
        password=body.password,
        remember=body.remember,
        user_agent=request.headers.get("user-agent"),
    )
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password incorrect.",
        )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=outcome.signed_cookie,
        max_age=outcome.max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(user=outcome.clerk)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> None:
    logout_service(session, request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=ClerkOut)
def me_endpoint(clerk: ClerkOut = Depends(get_current_clerk)) -> ClerkOut:
    return clerk
