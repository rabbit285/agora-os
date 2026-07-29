from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.dependencies import get_current_user
from app.identity import service
from app.identity.models import Session as SessionModel
from app.identity.models import User
from app.identity.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    OrganizationOut,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


@router.post("/signup", response_model=SignupResponse)
async def signup_endpoint(
    payload: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> SignupResponse:
    user, organization, session = await service.signup(
        db,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session.raw_token)  # type: ignore[attr-defined]
    return SignupResponse(
        user=UserOut.model_validate(user), organization=OrganizationOut.model_validate(organization)
    )


@router.post("/login", response_model=UserOut)
async def login_endpoint(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> UserOut:
    user, session = await service.login(
        db,
        payload.email,
        payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session.raw_token)  # type: ignore[attr-defined]
    return UserOut.model_validate(user)


@router.post("/logout")
async def logout_endpoint(
    response: Response,
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> dict[str, bool]:
    _, session = user_session
    await service.logout(db, session)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me_endpoint(
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> UserOut:
    user, _ = user_session
    return UserOut.model_validate(user)


@router.post("/forgot-password")
async def forgot_password_endpoint(
    payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, bool]:
    await service.request_password_reset(db, payload.email)
    # Always return success — never reveal whether the email is registered.
    return {"ok": True}


@router.post("/reset-password")
async def reset_password_endpoint(
    payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, bool]:
    await service.reset_password(db, payload.token, payload.new_password)
    return {"ok": True}
