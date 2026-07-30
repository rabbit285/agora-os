from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.invitations import accept_invitation
from app.db.session import get_db
from app.dependencies import get_current_user
from app.identity import service
from app.identity.models import Session as SessionModel
from app.identity.models import User
from app.identity.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MfaCodeRequest,
    MfaEnrollResponse,
    OrganizationOut,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    UserOut,
    VerifyEmailRequest,
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


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    user, session, mfa_required = await service.login(
        db,
        payload.email,
        payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session.raw_token)  # type: ignore[attr-defined]
    return LoginResponse(user=UserOut.model_validate(user), mfa_required=mfa_required)


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


@router.post("/resend-verification-email")
async def resend_verification_email_endpoint(
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> dict[str, bool]:
    user, _ = user_session
    await service.request_email_verification(db, user=user)
    await db.commit()
    return {"ok": True}


@router.post("/verify-email")
async def verify_email_endpoint(
    payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, bool]:
    await service.verify_email(db, payload.token)
    return {"ok": True}


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll_endpoint(
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> MfaEnrollResponse:
    user, _ = user_session
    provisioning_uri = await service.start_mfa_enrollment(db, user=user)
    return MfaEnrollResponse(provisioning_uri=provisioning_uri)


@router.post("/mfa/confirm")
async def mfa_confirm_endpoint(
    payload: MfaCodeRequest,
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> dict[str, bool]:
    user, _ = user_session
    try:
        await service.confirm_mfa_enrollment(db, user=user, code=payload.code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"ok": True}


@router.post("/mfa/disable")
async def mfa_disable_endpoint(
    payload: MfaCodeRequest,
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> dict[str, bool]:
    user, _ = user_session
    try:
        await service.disable_mfa(db, user=user, code=payload.code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"ok": True}


@router.post("/mfa/verify")
async def mfa_verify_endpoint(
    payload: MfaCodeRequest,
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> dict[str, bool]:
    user, session = user_session
    try:
        await service.verify_mfa_challenge(db, user=user, session=session, code=payload.code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"ok": True}


@router.post("/accept-invitation", response_model=AcceptInvitationResponse)
async def accept_invitation_endpoint(
    payload: AcceptInvitationRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AcceptInvitationResponse:
    try:
        user, organization, session = await accept_invitation(
            db,
            token=payload.token,
            full_name=payload.full_name,
            password=payload.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_session_cookie(response, session.raw_token)  # type: ignore[attr-defined]
    return AcceptInvitationResponse(
        user=UserOut.model_validate(user), organization=OrganizationOut.model_validate(organization)
    )
