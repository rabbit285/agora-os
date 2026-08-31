"""Who conducted the audit, and whose organization it was.

Two identities that a report must get right and had been getting wrong,
each for its own reason.

**The auditor.** "No linked account, therefore external" was the rule,
and it is not a fact about anybody. `auditor_user_id` only began being
written when the create form gained a picker; every audit before it
stored the auditor as text, so a colleague running an internal audit was
labelled external in the formal report. Internal-versus-external is a
question about organization membership, so it is answered from
membership — recorded on the audit at creation, reconciled from
membership for legacy rows, and left unresolved rather than guessed when
the evidence is ambiguous.

**The organization.** An audit report names the organization it is about,
and that name comes from the organization record and nowhere else. Never
a user's email, never an email domain, never the person who generated
the PDF. The record can still be unusable — a tenant created with an
email address in the name field is exactly the reported case — and where
it is, the report says the name is not configured rather than printing
somebody's email address as the name of a company.

Two identities that are also distinct from each other and from a third:
the person who pressed generate. They may be the same person; they are
never the same field.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Audit
from app.core.models import Membership, Organization
from app.identity.models import User

logger = logging.getLogger("agora.compliance.audit_identity")

INTERNAL = "internal"
EXTERNAL = "external"
AUDITOR_TYPES = (INTERNAL, EXTERNAL)

AUDITOR_TYPE_LABELS = {
    INTERNAL: "Internal",
    EXTERNAL: "External",
}

# What the report prints when the organization record cannot supply a
# name a reader would recognise. Deliberately not a fallback to anything
# derived from a person — an audit report that names a human's mailbox as
# the audited organization is worse than one that admits a gap.
UNCONFIGURED_ORGANIZATION = "Organization name not configured"

# Rough, and only used to reject. An organization is free to be called
# anything; what it must not be called in a formal report is somebody's
# email address, which is what a tenant created from a signup form with
# the email pasted into the organization field ends up with.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class AuditorIdentity:
    """The auditor, as a report states them.

    Structured rather than a formatted string: "Jane Smith (external)"
    reads as part of her name, and there is nowhere to put the firm she
    works for.
    """

    name: str | None
    # internal | external | None when nobody has established which.
    auditor_type: str | None
    type_label: str | None
    # The firm, for an external auditor. Never set for an internal one —
    # their organization is the one being audited.
    organization: str | None = None
    user_id: uuid.UUID | None = None
    # True when the audit predates the auditor type being recorded and
    # the name could not be matched to exactly one member. Reported as
    # unresolved; never quietly called external.
    unresolved: bool = False


def organization_display_name(organization: Organization | None) -> str | None:
    """The organization's name, or nothing.

    Returns None rather than a substitute, so every caller has to decide
    what to show — and none of them can accidentally fall through to an
    email address.
    """
    if organization is None:
        return None
    name = (organization.name or "").strip()
    if not name:
        return None
    if _EMAIL.match(name):
        # The reported case: a tenant whose name field holds
        # "xwarren@outlook.com". The record is real and the value is not
        # a company name, so it is treated as unconfigured.
        logger.info(
            "Organization %s has an email address in its name field; "
            "reporting it as unconfigured",
            organization.id,
        )
        return None
    return name


async def resolve_auditor(db: AsyncSession, *, audit: Audit) -> AuditorIdentity:
    """Who conducted this audit.

    Reads what was recorded. Resolves nothing on the fly except the
    auditor's current display name when an account is linked, because a
    person who changes their name should not make an old audit unreadable
    — while the identity itself stays exactly as recorded.
    """
    name = (audit.auditor_name or "").strip() or None
    auditor_type = audit.auditor_type if audit.auditor_type in AUDITOR_TYPES else None

    if audit.auditor_user_id is not None:
        person = await db.get(User, audit.auditor_user_id)
        if person is not None:
            name = person.full_name or person.email or name
        # A linked account is a member of the organization, so internal
        # regardless of what an older row happens to say.
        auditor_type = INTERNAL

    if auditor_type == EXTERNAL:
        return AuditorIdentity(
            name=name,
            auditor_type=EXTERNAL,
            type_label=AUDITOR_TYPE_LABELS[EXTERNAL],
            organization=(audit.auditor_organization or "").strip() or None,
        )
    if auditor_type == INTERNAL:
        return AuditorIdentity(
            name=name,
            auditor_type=INTERNAL,
            type_label=AUDITOR_TYPE_LABELS[INTERNAL],
            user_id=audit.auditor_user_id,
        )

    # Nothing recorded. The audit predates the field and its name matched
    # no member, or matched more than one. Both are "we do not know",
    # which is what the report says.
    return AuditorIdentity(
        name=name,
        auditor_type=None,
        type_label=None,
        unresolved=bool(name),
    )


async def members_by_name(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, list[User]]:
    """Everybody in the organization, keyed by normalised display name.

    A list per key, because two people can share a name and the whole
    point of this is refusing to pick between them.
    """
    rows = (
        await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == organization_id)
        )
    ).scalars().all()
    grouped: dict[str, list[User]] = {}
    for user in rows:
        key = (user.full_name or "").strip().lower()
        if key:
            grouped.setdefault(key, []).append(user)
    return grouped


@dataclass
class ReconcileResult:
    """What a repair pass established, and what it refused to."""

    linked: int = 0
    already_resolved: int = 0
    # Named rather than counted: somebody has to look at these, and a
    # number tells them nothing about which.
    ambiguous: list[str] = None  # type: ignore[assignment]
    unmatched: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ambiguous is None:
            self.ambiguous = []
        if self.unmatched is None:
            self.unmatched = []


async def reconcile_auditors(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> ReconcileResult:
    """Link legacy auditors to the accounts they unambiguously are.

    The safety is the ambiguity check, not the match. A name matching one
    member of the organization is evidence; a name matching two is
    evidence of nothing, and attributing an audit to the wrong person is
    a worse outcome than leaving it unresolved. Neither case is ever
    resolved to `external` — nothing here has established that anybody
    was external.
    """
    result = ReconcileResult()
    audits = (
        await db.execute(
            select(Audit).where(Audit.organization_id == organization_id)
        )
    ).scalars().all()

    pending = [
        audit
        for audit in audits
        if audit.auditor_user_id is None
        and audit.auditor_type not in AUDITOR_TYPES
        and (audit.auditor_name or "").strip()
    ]
    result.already_resolved = len(audits) - len(pending)
    if not pending:
        return result

    by_name = await members_by_name(db, organization_id=organization_id)
    for audit in pending:
        key = (audit.auditor_name or "").strip().lower()
        candidates = by_name.get(key, [])
        if len(candidates) == 1:
            audit.auditor_user_id = candidates[0].id
            audit.auditor_type = INTERNAL
            result.linked += 1
        elif len(candidates) > 1:
            result.ambiguous.append(audit.auditor_name or "")
        else:
            result.unmatched.append(audit.auditor_name or "")

    if result.linked:
        await db.flush()
    logger.info(
        "Auditor reconciliation for %s: linked=%d ambiguous=%d unmatched=%d",
        organization_id,
        result.linked,
        len(result.ambiguous),
        len(result.unmatched),
    )
    return result


async def is_member(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Whether this account belongs to this organization.

    Checked at creation so an audit can never be recorded as internal
    against somebody who is not a member.
    """
    found = (
        await db.execute(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
            )
        )
    ).scalar()
    return bool(found)


__all__ = [
    "AUDITOR_TYPES",
    "AUDITOR_TYPE_LABELS",
    "EXTERNAL",
    "INTERNAL",
    "UNCONFIGURED_ORGANIZATION",
    "AuditorIdentity",
    "ReconcileResult",
    "is_member",
    "members_by_name",
    "organization_display_name",
    "reconcile_auditors",
    "resolve_auditor",
]
