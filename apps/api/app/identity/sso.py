"""Real Sign-in-with-Google / Sign-in-with-Microsoft SSO (spec §59's
"SSO" — distinct from SAML/SCIM, which carry the spec's own "architecture"
qualifier in that same section and remain disclosed as unbuilt in
docs/KNOWN_LIMITATIONS.md).

Reuses the exact same OAuth adapters `app.integrations.adapters` already
has for HubSpot/Google/Microsoft/etc. — genuinely the same real
`exchange_code_for_tokens` HTTP call, not a second implementation — but
requests a minimal identity-only scope (`openid email` for Google,
`openid email profile User.Read` for Microsoft) rather than the broader
Calendar/Gmail/Drive/Mail scopes those adapters request for Integrations
connections, since a login flow has no business asking for calendar
access. `exchange_code_for_tokens` itself doesn't care what scope was
actually granted, so this is safe to build independently of the
Integrations authorization URL. A separate identity-fetch call (real,
against each provider's real userinfo/me endpoint) resolves the real
email address a login needs, which the Integrations-oriented
`HealthResult`/`SyncResult` shapes were never designed to carry.

Never uses `MockOAuthAdapter`: unlike an Integrations connection (where a
mock is honestly labeled demo data), fabricating a login identity would
mean creating a real User/Session from a fake email — `start_sso_login`
refuses outright when a provider isn't really configured, the same way
every other credential-gated capability in this build refuses rather than
simulates (spec §82).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.billing.service import ensure_plan_catalog, start_trial
from app.config import settings
from app.core.models import LegalEntity, Membership, MembershipRole, Organization
from app.core.rbac import ensure_system_roles, get_system_role
from app.db.base import as_aware_utc
from app.identity.models import Session as SessionModel
from app.identity.models import SsoLoginAttempt, User
from app.identity.service import _unique_slug, create_session
from app.integrations.adapters import get_oauth_adapter, is_provider_configured
from app.security import generate_token, hash_password, hash_token

logger = logging.getLogger("agora.identity")

SSO_PROVIDERS = frozenset({"google", "microsoft"})
STATE_TTL = timedelta(minutes=10)

_GOOGLE_SCOPES = "openid email"
_MICROSOFT_SCOPES = "openid email profile User.Read"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_MICROSOFT_ME_URL = "https://graph.microsoft.com/v1.0/me"
REQUEST_TIMEOUT_SECONDS = 15.0


def _redirect_uri(provider: str) -> str:
    return f"{settings.api_url}/api/v1/auth/sso/{provider}/callback"


def _validate_provider(provider: str) -> None:
    if provider not in SSO_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown SSO provider")


async def start_sso_login(db: AsyncSession, *, provider: str) -> str:
    _validate_provider(provider)
    if not is_provider_configured(provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{provider} SSO is not configured on this deployment",
        )

    state = generate_token()
    db.add(
        SsoLoginAttempt(
            state_token_hash=hash_token(state),
            provider=provider,
            expires_at=datetime.now(UTC) + STATE_TTL,
        )
    )
    await db.commit()

    scopes = _GOOGLE_SCOPES if provider == "google" else _MICROSOFT_SCOPES
    redirect_uri = _redirect_uri(provider)
    if provider == "google":
        url = httpx.URL(
            "https://accounts.google.com/o/oauth2/v2/auth",
            params={
                "client_id": settings.google_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scopes,
                "state": state,
            },
        )
    else:
        url = httpx.URL(
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            params={
                "client_id": settings.microsoft_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "response_mode": "query",
                "scope": scopes,
                "state": state,
            },
        )
    return str(url)


async def _consume_state(db: AsyncSession, *, provider: str, state: str) -> None:
    attempt = (
        await db.execute(
            select(SsoLoginAttempt).where(SsoLoginAttempt.state_token_hash == hash_token(state))
        )
    ).scalar_one_or_none()
    if (
        attempt is None
        or attempt.provider != provider
        or attempt.consumed_at is not None
        or as_aware_utc(attempt.expires_at) < datetime.now(UTC)
    ):
        raise ValueError("Invalid or expired SSO login attempt")
    attempt.consumed_at = datetime.now(UTC)


async def _fetch_identity(provider: str, access_token: str) -> tuple[str, str | None]:
    """Returns (email, full_name). Raises ValueError if the provider
    didn't return a usable email — some Google/Microsoft accounts have no
    primary email on the identity scope, and a login can't proceed
    without one."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        if provider == "google":
            response = await client.get(
                _GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            body = response.json()
            email = body.get("email")
            name = body.get("name")
        else:
            response = await client.get(
                _MICROSOFT_ME_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            body = response.json()
            email = body.get("mail") or body.get("userPrincipalName")
            name = body.get("displayName")
    if not email:
        raise ValueError(f"{provider} did not return an email address for this account")
    return email.lower(), name


async def _provision_user_and_organization(
    db: AsyncSession, *, email: str, full_name: str | None
) -> tuple[User, Organization]:
    """First-time SSO login — no invitation, no existing account: mirrors
    app.identity.service.signup exactly (new Org, default LegalEntity,
    org_admin Membership), except the password is a random, never-shared
    value the user can never type — this account can only ever log in via
    SSO, which is honest given how it was created."""
    await ensure_system_roles(db)
    await ensure_plan_catalog(db)

    user = User(
        email=email,
        hashed_password=hash_password(generate_token()),
        full_name=full_name,
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()

    org_name = full_name or email.split("@")[0]
    slug = await _unique_slug(db, org_name)
    organization = Organization(name=org_name, slug=slug)
    db.add(organization)
    await db.flush()

    db.add(LegalEntity(organization_id=organization.id, name=org_name, is_default=True))

    # Same 14-day Starter trial a password signup gets.
    await start_trial(db, organization_id=organization.id)

    membership = Membership(organization_id=organization.id, user_id=user.id, status="active")
    db.add(membership)
    await db.flush()

    org_admin_role = await get_system_role(db, "org_admin")
    db.add(MembershipRole(membership_id=membership.id, role_id=org_admin_role.id))

    return user, organization


async def _first_active_organization_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        select(Membership.organization_id).where(
            Membership.user_id == user_id, Membership.status == "active"
        )
    )
    row = result.first()
    return row[0] if row else None


async def complete_sso_login(
    db: AsyncSession,
    *,
    provider: str,
    code: str,
    state: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[User, SessionModel, bool, bool]:
    """Returns (user, session, mfa_required, is_new_user)."""
    _validate_provider(provider)
    await _consume_state(db, provider=provider, state=state)

    adapter = get_oauth_adapter(provider)
    token_result = await adapter.exchange_code_for_tokens(
        code=code, redirect_uri=_redirect_uri(provider)
    )
    email, full_name = await _fetch_identity(provider, token_result.access_token)

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    is_new_user = user is None
    organization_id: uuid.UUID | None
    if user is None:
        user, organization = await _provision_user_and_organization(
            db, email=email, full_name=full_name
        )
        organization_id = organization.id
    else:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
        organization_id = await _first_active_organization_id(db, user.id)
        # spec §64 entitlement enforcement (sso_enabled) — only for an
        # existing user logging into an existing org. A brand-new,
        # auto-provisioned org (the `if` branch above) is deliberately
        # exempt: it just used SSO to sign up, so checking its
        # freshly-assigned default plan's sso_enabled would be a
        # chicken-and-egg rejection of the very login that created it.
        if organization_id is not None:
            from app.billing.service import check_boolean_entitlement

            if not await check_boolean_entitlement(
                db, organization_id=organization_id, key="sso_enabled"
            ):
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="SSO is not included in this organization's current plan",
                )

    mfa_required = user.mfa_enabled
    session = await create_session(
        db,
        user=user,
        organization_id=organization_id,
        ip_address=ip_address,
        user_agent=user_agent,
        mfa_verified=not mfa_required,
    )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=user.id,
        action="auth.sso_login" if not is_new_user else "auth.sso_signup",
        object_type="user",
        object_id=str(user.id),
        ip_address=ip_address,
        user_agent=user_agent,
        after_state={"provider": provider},
    )
    await db.commit()
    return user, session, mfa_required, is_new_user
