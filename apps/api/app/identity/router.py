from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.invitations import accept_invitation, decline_invitation, get_invitation_preview
from app.db.session import get_db
from app.dependencies import get_current_user
from app.identity import service, sso
from app.identity.models import Session as SessionModel
from app.identity.models import User
from app.identity.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    ForgotPasswordRequest,
    InvitationPreviewOut,
    LoginRequest,
    LoginResponse,
    MfaCodeRequest,
    MfaEnrollResponse,
    OrganizationOut,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    SsoProviderStatusOut,
    SsoStartResponse,
    UserOut,
    VerifyEmailRequest,
)
from app.integrations.adapters import is_provider_configured

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


@router.get("/sso/providers", response_model=list[SsoProviderStatusOut])
async def sso_providers_endpoint() -> list[SsoProviderStatusOut]:
    """Public — no auth, since this backs the pre-login page. Reveals only
    a boolean, the same non-secret `configured` field the (authenticated)
    Integrations provider catalog already exposes."""
    return [
        SsoProviderStatusOut(provider=provider, configured=is_provider_configured(provider))
        for provider in sso.SSO_PROVIDERS
    ]


@router.get("/sso/{provider}/start", response_model=SsoStartResponse)
async def sso_start_endpoint(
    provider: str, db: AsyncSession = Depends(get_db)
) -> SsoStartResponse:
    """No session dependency — this is the pre-login entry point (spec
    §59 SSO). Raises 400 if the provider isn't really configured rather
    than returning a URL that would fail at Google/Microsoft."""
    url = await sso.start_sso_login(db, provider=provider)
    return SsoStartResponse(authorization_url=url)


@router.get("/sso/{provider}/callback")
async def sso_callback_endpoint(
    provider: str,
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """No session dependency — a top-level browser redirect from the
    provider. `state` (not a cookie) proves this belongs to a login this
    server actually started, the same pattern
    `app.routers.integrations.oauth_callback` uses. Sets the session
    cookie directly on the returned `RedirectResponse` rather than the
    usual injected `response: Response` dependency — FastAPI does not
    merge that dependency's cookies onto a `Response` subclass an endpoint
    returns directly, only onto a response it constructs itself from a
    plain return value."""
    try:
        user, session, mfa_required, is_new_user = await sso.complete_sso_login(
            db,
            provider=provider,
            code=code,
            state=state,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except (ValueError, HTTPException) as exc:
        await db.rollback()
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return RedirectResponse(url=f"{settings.app_url}/login?error={quote(str(detail))}")

    if mfa_required:
        redirect = RedirectResponse(url=f"{settings.app_url}/mfa-challenge")
    elif is_new_user:
        redirect = RedirectResponse(url=f"{settings.app_url}/onboarding")
    else:
        redirect = RedirectResponse(url=f"{settings.app_url}/dashboard")
    _set_session_cookie(redirect, session.raw_token)  # type: ignore[attr-defined]
    return redirect


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


@router.get("/invitations/{token}", response_model=InvitationPreviewOut)
async def preview_invitation_endpoint(
    token: str, db: AsyncSession = Depends(get_db)
) -> InvitationPreviewOut:
    preview = await get_invitation_preview(db, token=token)
    if preview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return preview


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


@router.post("/invitations/{token}/decline", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def decline_invitation_endpoint(token: str, db: AsyncSession = Depends(get_db)) -> None:
    try:
        await decline_invitation(db, token=token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
