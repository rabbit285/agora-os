from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.config import settings
from app.core.invitations import create_invitation
from app.core.models import (
    Invitation,
    LegalEntity,
    Membership,
    MembershipRole,
    Organization,
    Permission,
    Role,
    RolePermission,
    Team,
)
from app.identity.models import User
from app.core.organization_deletion import (
    cancel_organization_deletion,
    execute_organization_deletion,
    request_organization_deletion,
)
from app.core.organization_export import build_organization_export
from app.core.schemas import (
    LegalEntityCreate,
    LegalEntityOut,
    LegalEntityUpdate,
    MembershipOut,
    OrganizationPersonOut,
    OrganizationDeletionConfirm,
    OrganizationSettingsOut,
    OrganizationSettingsUpdate,
    RoleOut,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)
from app.core.storage import build_storage_key, presign_download, upload_object
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.identity.schemas import InvitationCreate, InvitationOut
from app.reporting.rendering import RENDERERS
from app.reporting.schemas import REPORT_FORMATS, ReportDownloadOut

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.get("/current", response_model=OrganizationSettingsOut)
async def get_current_organization(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> Organization:
    org = await db.get(Organization, context.organization_id)
    assert org is not None  # tenant resolution already guarantees existence
    return org


@router.patch("/current", response_model=OrganizationSettingsOut)
async def update_current_organization(
    payload: OrganizationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> Organization:
    org = await db.get(Organization, context.organization_id)
    assert org is not None
    before_name = org.name
    before_webhook = org.notification_webhook_url
    org.name = payload.name
    if "notification_webhook_url" in payload.model_fields_set:
        org.notification_webhook_url = payload.notification_webhook_url
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.settings.updated",
        object_type="organization",
        object_id=str(org.id),
        before_state={"name": before_name, "notification_webhook_url": before_webhook},
        after_state={"name": org.name, "notification_webhook_url": org.notification_webhook_url},
    )
    await db.commit()
    await db.refresh(org)
    return org


def _check_confirm_name(organization: Organization, confirm_name: str) -> None:
    if confirm_name != organization.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm_name does not match the organization's current name",
        )


@router.post("/current/deletion-request", response_model=OrganizationSettingsOut)
async def request_current_organization_deletion(
    payload: OrganizationDeletionConfirm,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> Organization:
    """spec §B5 "Customer Data Control": export; deletion. Real,
    visible, cancellable, audited precursor state — does not itself
    delete anything; see POST .../deletion-request/execute for the
    actual irreversible purge, which requires this to already be set."""
    org = await db.get(Organization, context.organization_id)
    assert org is not None
    _check_confirm_name(org, payload.confirm_name)
    org = await request_organization_deletion(db, organization_id=context.organization_id)
    assert org.deletion_requested_at is not None
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.deletion.requested",
        object_type="organization",
        object_id=str(org.id),
        after_state={"deletion_requested_at": org.deletion_requested_at.isoformat()},
    )
    await db.commit()
    await db.refresh(org)
    return org


@router.post("/current/deletion-request/cancel", response_model=OrganizationSettingsOut)
async def cancel_current_organization_deletion(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> Organization:
    org = await cancel_organization_deletion(db, organization_id=context.organization_id)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.deletion.cancelled",
        object_type="organization",
        object_id=str(org.id),
    )
    await db.commit()
    await db.refresh(org)
    return org


@router.post("/current/deletion-request/execute", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def execute_current_organization_deletion(
    payload: OrganizationDeletionConfirm,
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> None:
    """The actual, irreversible deletion — every row this organization
    owns across every module, gone in one transaction. Requires a
    pending deletion request (POST .../deletion-request) to already
    exist, plus the organization's exact current name typed again as a
    second, separate confirmation — the same two-step, type-the-name
    danger-zone pattern real production systems use for exactly this
    class of action."""
    org = await db.get(Organization, context.organization_id)
    assert org is not None
    if org.deletion_requested_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No deletion request is pending for this organization. "
            "Call POST /organizations/current/deletion-request first.",
        )
    _check_confirm_name(org, payload.confirm_name)
    await execute_organization_deletion(
        db, organization_id=context.organization_id, executed_by=context.user.id
    )
    # The caller's own `sessions` row was just deleted along with every
    # other organization-scoped table above, but the browser's cookie
    # itself survives that server-side purge — without clearing it here,
    # `middleware.ts`'s cookie-presence check treats the browser as still
    # authenticated and bounces it away from /login right back toward the
    # now-nonexistent org.
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/current/data-export", response_model=ReportDownloadOut)
async def export_current_organization_data(
    format: str = Query(default="xlsx"),
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> ReportDownloadOut:
    """spec §B5 "Customer Data Control": export. A real, downloadable
    bundle of this organization's own data across every module — reuses
    app.reporting's ReportSection/ReportContent shape and its 4 real
    renderers outright rather than a second export pipeline."""
    if format not in REPORT_FORMATS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown format: {format}")
    content = await build_organization_export(db, context.organization_id)
    file_bytes = RENDERERS[format](content)
    storage_key = build_storage_key(context.organization_id, f"organization_data_export.{format}")
    upload_object(storage_key, file_bytes, REPORT_FORMATS[format])
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.data_export.generated",
        object_type="organization",
        object_id=str(context.organization_id),
        after_state={"format": format},
    )
    await db.commit()
    return ReportDownloadOut(download_url=presign_download(storage_key))


@router.get("/current/my-permissions", response_model=list[str])
async def get_my_permissions(
    context: OrgContext = Depends(get_org_context),
) -> list[str]:
    """The current membership's resolved permission keys (spec §72 Global
    Create needs to filter its options by permission client-side, the same
    set `require_permission()` already checks server-side on every write)."""
    return sorted(context.permissions)


@router.get("/current/roles", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[RoleOut]:
    """spec §54's default role list, each with its real granted permission
    keys — a reference view (`/settings/roles`), not an editor: every role
    here is a system role (`organization_id IS NULL`, shared across every
    organization in this deployment), so editing one from a single org's
    settings page would silently change what every *other* organization's
    same-named role can do. This build has no per-org custom roles yet
    (spec §54 doesn't ask for one), so there is nothing safe to edit —
    disclosed in docs/KNOWN_LIMITATIONS.md rather than building an editor
    that would mutate shared state."""
    roles = (
        (await db.execute(select(Role).where(Role.organization_id.is_(None)).order_by(Role.key)))
        .scalars()
        .all()
    )
    grants = (
        await db.execute(
            select(RolePermission.role_id, Permission.key).join(
                Permission, Permission.id == RolePermission.permission_id
            )
        )
    ).all()
    permissions_by_role: dict[uuid.UUID, list[str]] = {}
    for role_id, permission_key in grants:
        permissions_by_role.setdefault(role_id, []).append(permission_key)
    return [
        RoleOut(key=role.key, name=role.name, permissions=sorted(permissions_by_role.get(role.id, [])))
        for role in roles
    ]


@router.get("/current/members", response_model=list[MembershipOut])
async def list_members(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> list[MembershipOut]:
    rows = (
        await db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == context.organization_id)
        )
    ).all()

    out: list[MembershipOut] = []
    for membership, user in rows:
        role_result = await db.execute(
            select(Role.key)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(MembershipRole.membership_id == membership.id)
        )
        roles = [row[0] for row in role_result.all()]
        out.append(
            MembershipOut(
                id=membership.id,
                user_id=membership.user_id,
                status=membership.status,
                roles=roles,
                full_name=user.full_name,
                email=user.email,
            )
        )
    return out


@router.get("/current/people", response_model=list[OrganizationPersonOut])
async def list_people(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[OrganizationPersonOut]:
    """The colleagues a form can offer, and nothing else about them.

    Separate from `/members`, which needs `org.users.manage` because it
    exposes roles and membership state. Choosing who ran an audit — or
    who owns a task — is not user administration, and a compliance
    manager should not need the power to change people's roles in order
    to name one of them in a form.

    Name and email only, and only active members: enough to pick a person
    and no more.
    """
    rows = (
        await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == context.organization_id,
                Membership.status == "active",
                User.is_active.is_(True),
            )
            .order_by(User.full_name.asc(), User.email.asc())
        )
    ).scalars().all()
    return [
        OrganizationPersonOut(
            id=user.id, full_name=user.full_name, email=user.email
        )
        for user in rows
    ]


@router.get("/current/invitations", response_model=list[InvitationOut])
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> list[Invitation]:
    result = await db.execute(
        select(Invitation)
        .where(Invitation.organization_id == context.organization_id)
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/current/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED
)
async def create_invitation_endpoint(
    payload: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> Invitation:
    org = await db.get(Organization, context.organization_id)
    assert org is not None
    try:
        invitation = await create_invitation(
            db,
            organization=org,
            email=payload.email,
            role_key=payload.role_key,
            invited_by=context.user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(invitation)
    return invitation


@router.post("/current/invitations/{invitation_id}/revoke", response_model=InvitationOut)
async def revoke_invitation_endpoint(
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> Invitation:
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invitation has already been accepted"
        )
    invitation.revoked_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.invitation.revoked",
        object_type="invitation",
        object_id=str(invitation.id),
    )
    await db.commit()
    await db.refresh(invitation)
    return invitation


# --- Multi-entity (spec §53's "Support:" tier) -----------------------------


async def _get_org_legal_entity(
    db: AsyncSession, entity_id: uuid.UUID, organization_id: uuid.UUID
) -> LegalEntity:
    entity = await db.get(LegalEntity, entity_id)
    if entity is None or entity.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal entity not found")
    return entity


@router.get("/current/legal-entities", response_model=list[LegalEntityOut])
async def list_legal_entities(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> list[LegalEntity]:
    result = await db.execute(
        select(LegalEntity)
        .where(LegalEntity.organization_id == context.organization_id)
        .order_by(LegalEntity.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/current/legal-entities", response_model=LegalEntityOut, status_code=status.HTTP_201_CREATED
)
async def create_legal_entity(
    payload: LegalEntityCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> LegalEntity:
    entity = LegalEntity(
        organization_id=context.organization_id, name=payload.name, country=payload.country
    )
    db.add(entity)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.legal_entity.created",
        object_type="legal_entity",
        object_id=str(entity.id),
        after_state={"name": entity.name, "country": entity.country},
    )
    await db.commit()
    await db.refresh(entity)
    return entity


@router.patch("/current/legal-entities/{entity_id}", response_model=LegalEntityOut)
async def update_legal_entity(
    entity_id: uuid.UUID,
    payload: LegalEntityUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> LegalEntity:
    entity = await _get_org_legal_entity(db, entity_id, context.organization_id)
    before_state = {"name": entity.name, "country": entity.country, "is_default": entity.is_default}
    if payload.name is not None:
        entity.name = payload.name
    if payload.country is not None:
        entity.country = payload.country
    if payload.is_default is True:
        # Exactly one default per organization — demote every other entity.
        others = await db.execute(
            select(LegalEntity).where(
                LegalEntity.organization_id == context.organization_id,
                LegalEntity.id != entity.id,
            )
        )
        for other in others.scalars().all():
            other.is_default = False
        entity.is_default = True
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.legal_entity.updated",
        object_type="legal_entity",
        object_id=str(entity.id),
        before_state=before_state,
        after_state={"name": entity.name, "country": entity.country, "is_default": entity.is_default},
    )
    await db.commit()
    await db.refresh(entity)
    return entity


@router.delete("/current/legal-entities/{entity_id}", response_model=LegalEntityOut)
async def archive_legal_entity(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> LegalEntity:
    # Archival, not destructive delete (spec §73).
    entity = await _get_org_legal_entity(db, entity_id, context.organization_id)
    if entity.is_default:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot archive the default legal entity — set another one as default first",
        )
    entity.is_active = False
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.legal_entity.archived",
        object_type="legal_entity",
        object_id=str(entity.id),
    )
    await db.commit()
    await db.refresh(entity)
    return entity


async def _get_org_team(db: AsyncSession, team_id: uuid.UUID, organization_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None or team.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.get("/current/teams", response_model=list[TeamOut])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> list[Team]:
    result = await db.execute(
        select(Team).where(Team.organization_id == context.organization_id).order_by(Team.created_at)
    )
    return list(result.scalars().all())


@router.post("/current/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> Team:
    if payload.legal_entity_id is not None:
        await _get_org_legal_entity(db, payload.legal_entity_id, context.organization_id)
    team = Team(
        organization_id=context.organization_id,
        name=payload.name,
        legal_entity_id=payload.legal_entity_id,
    )
    db.add(team)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.team.created",
        object_type="team",
        object_id=str(team.id),
        after_state={"name": team.name, "legal_entity_id": str(team.legal_entity_id or "")},
    )
    await db.commit()
    await db.refresh(team)
    return team


@router.patch("/current/teams/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> Team:
    team = await _get_org_team(db, team_id, context.organization_id)
    before_state = {"name": team.name, "legal_entity_id": str(team.legal_entity_id or "")}
    if payload.name is not None:
        team.name = payload.name
    if "legal_entity_id" in payload.model_fields_set:
        if payload.legal_entity_id is not None:
            await _get_org_legal_entity(db, payload.legal_entity_id, context.organization_id)
        team.legal_entity_id = payload.legal_entity_id
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.team.updated",
        object_type="team",
        object_id=str(team.id),
        before_state=before_state,
        after_state={"name": team.name, "legal_entity_id": str(team.legal_entity_id or "")},
    )
    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/current/teams/{team_id}", response_model=TeamOut)
async def archive_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.entities.manage")),
) -> Team:
    team = await _get_org_team(db, team_id, context.organization_id)
    team.is_active = False
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.team.archived",
        object_type="team",
        object_id=str(team.id),
    )
    await db.commit()
    await db.refresh(team)
    return team
