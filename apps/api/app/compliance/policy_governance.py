"""Turning an uploaded policy into a governed one, without retyping it.

The old flow asked the customer to upload `03_AI_Governance_Policy.docx`,
watch Veyntra read it, classify it, extract ten pieces of evidence and map
them to ten controls — and then go to another screen, press "Add policy",
and type "AI Governance Policy" into a box. The product already knew the
title. It already had the file. Asking again is asking someone to do data
entry the system could have done, which is the opposite of what they
bought.

So classification creates the governance record. What it does **not** do
is fill it in:

- **Detection is not approval.** A detected policy starts at
  `needs_review` with no owner, no approver and no review date. The
  product cannot know who owns a document or whether the organization
  signed it off, and writing a plausible answer would be a fabricated
  compliance record — the one thing this system must never produce.
- **Nothing is invented.** A version is recorded only if the document
  states one. Everything else stays empty and the UI asks.

Idempotent by document. Re-processing a file finds its existing policy
rather than creating a second one, which matters because the backfill can
run repeatedly and documents get reanalysed.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Policy, PolicyVersion
from app.core.models import File

logger = logging.getLogger("agora.compliance.policy_governance")

# What a governance record can be in. Named for the lifecycle rather than
# for a publish button — "draft/published" could not express "somebody
# owns this, nobody has approved it, and a review is overdue".
POLICY_STATUSES = (
    "needs_review",
    "draft",
    "approved",
    "review_due",
    "superseded",
    "retired",
)

# Words that mean "this document is a policy" in the classifier's own
# output. The classifier describes a document in the words the document
# uses, so this reads its answer rather than the filename — a file called
# `final_v3.docx` containing an access control policy has to be caught,
# and `policy_template_notes.docx` containing meeting notes must not be.
_POLICY_TYPE_WORDS = (
    "policy",
    "procedure",
    "standard",
    "guideline",
    "charter",
    "runbook",
    "code of conduct",
)

# Types that name a document which is *about* policy without being one.
_NOT_A_POLICY = (
    "policy template",
    "policy checklist",
    "gap analysis",
    "assessment",
    "questionnaire",
    "training record",
    "completion record",
    "register",
    "log",
    "report",
)

_VERSION_PATTERN = re.compile(
    r"\b(?:version|v|rev(?:ision)?)[\s.:]*([0-9]+(?:\.[0-9]+){0,2})\b", re.IGNORECASE
)


def looks_like_a_policy(document_type: str | None) -> bool:
    """Whether the classifier's description names a policy document.

    Reads the classification, never the filename: `document_type` is what
    the model concluded the document *is*, from its content.
    """
    if not document_type:
        return False
    lowered = document_type.lower()
    if any(phrase in lowered for phrase in _NOT_A_POLICY):
        return False
    return any(word in lowered for word in _POLICY_TYPE_WORDS)


def detect_version(text: str | None) -> str | None:
    """A version, only if the document states one.

    Returns None rather than "1.0" when nothing is found. A default here
    would put a version number the customer never wrote into a record an
    auditor may read.
    """
    if not text:
        return None
    match = _VERSION_PATTERN.search(text[:4000])
    return match.group(1) if match else None


def _filename_title(file_record: File) -> str:
    """A title from the filename: `03_AI_Governance_Policy.docx` becomes
    "AI Governance Policy". The leading sort number and the extension are
    artefacts of somebody's folder, not part of the name."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", file_record.original_filename)
    stem = re.sub(r"^[\d\s._-]+", "", stem)
    return (stem.replace("_", " ").replace("-", " ").strip() or "Untitled policy")[:300]


def _title_from(file_record: File) -> str:
    """The policy's name, preferring what the document called itself.

    Only when that is *specific*. The classifier described one real upload
    as simply "policy", which is a category rather than a name — a list
    row reading "policy" tells the reader nothing, and two such documents
    would collide into one governance record. Where the classification is
    that generic the filename is genuinely more informative, so it wins.
    """
    described = (file_record.document_type or "").strip()
    generic = described.lower().strip(" .-")
    is_generic = generic in _POLICY_TYPE_WORDS or len(generic.split()) < 2
    if described and not is_generic:
        return described[:300]
    return _filename_title(file_record)


async def _existing_for_document(
    db: AsyncSession, *, organization_id: uuid.UUID, file_id: uuid.UUID
) -> Policy | None:
    """Any policy already pointing at this document, current or superseded.

    Checked through `policy_versions` as well as `Policy.file_id`, so
    re-processing a file that has since been superseded does not resurrect
    it as a second policy.
    """
    current = (
        await db.execute(
            select(Policy).where(
                Policy.organization_id == organization_id, Policy.file_id == file_id
            )
        )
    ).scalars().first()
    if current is not None:
        return current

    version_row = (
        await db.execute(
            select(Policy)
            .join(PolicyVersion, PolicyVersion.policy_id == Policy.id)
            .where(
                Policy.organization_id == organization_id,
                PolicyVersion.file_id == file_id,
            )
        )
    ).scalars().first()
    return version_row


async def _existing_by_title(
    db: AsyncSession, *, organization_id: uuid.UUID, title: str
) -> Policy | None:
    """A policy already governing this subject, whatever document it has.

    This is what makes re-uploading `AI_Governance_Policy_v2.docx` a new
    *version* rather than a second policy. Matched on the normalised
    title, which is the strongest signal available without asking.
    """
    normalised = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if not normalised:
        return None
    candidates = list(
        (
            await db.execute(
                select(Policy).where(Policy.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    for candidate in candidates:
        if re.sub(r"[^a-z0-9]+", " ", candidate.title.lower()).strip() == normalised:
            return candidate
    return None


async def ensure_policy_for_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    document_text: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Policy | None:
    """Create or link the governance record for a policy document.

    Returns None when the document is not a policy — most uploads are not,
    and a governance record for a training register would be noise in the
    one list that is supposed to be short.

    Three outcomes, in order of preference: the document already has a
    policy (return it), a policy with the same title exists (suggest this
    document as a new version, without switching to it), or neither
    (create the record).
    """
    if not looks_like_a_policy(file_record.document_type):
        return None

    existing = await _existing_for_document(
        db, organization_id=organization_id, file_id=file_record.id
    )
    if existing is not None:
        return existing

    title = _title_from(file_record)
    same_subject = await _existing_by_title(
        db, organization_id=organization_id, title=title
    )
    if same_subject is not None:
        # A newer document for a policy that already exists. Recorded as a
        # candidate version and left for a person to confirm: silently
        # swapping the document under an approved policy would change what
        # the organization is asserting without anyone deciding to.
        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="compliance.policy.new_version_detected",
            object_type="policy",
            object_id=str(same_subject.id),
            after_state={
                "file_id": str(file_record.id),
                "filename": file_record.original_filename,
                "current_file_id": str(same_subject.file_id) if same_subject.file_id else None,
            },
        )
        return same_subject

    policy = Policy(
        organization_id=organization_id,
        title=title,
        file_id=file_record.id,
        # Detected, not approved. Everything below is left for a person.
        status="needs_review",
        category=file_record.document_domain,
        version=detect_version(document_text),
        detected_automatically=True,
    )
    db.add(policy)
    await db.flush()

    db.add(
        PolicyVersion(
            organization_id=organization_id,
            policy_id=policy.id,
            file_id=file_record.id,
            version=policy.version,
            status="current",
        )
    )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.policy.detected",
        object_type="policy",
        object_id=str(policy.id),
        after_state={
            "title": policy.title,
            "document_type": file_record.document_type,
            "file_id": str(file_record.id),
            "version": policy.version,
        },
    )
    logger.info("Detected policy %r from %s", policy.title, file_record.original_filename)
    return policy


async def promote_document_to_current_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    policy: Policy,
    file_record: File,
    actor_user_id: uuid.UUID | None,
    version: str | None = None,
) -> Policy:
    """Make this document the policy's current version, keeping the old one.

    The previous version is marked superseded, never deleted — "what did
    your retention policy say in March" is a question an auditor asks.
    Approval does not carry over: a new document is a new thing to sign
    off, and inheriting the old approval would attach somebody's name to
    text they never read.
    """
    now = datetime.now(UTC)
    previous_file_id = policy.file_id

    if previous_file_id is not None:
        current_rows = list(
            (
                await db.execute(
                    select(PolicyVersion).where(
                        PolicyVersion.policy_id == policy.id,
                        PolicyVersion.status == "current",
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in current_rows:
            row.status = "superseded"
            row.superseded_at = now

    policy.file_id = file_record.id
    policy.version = version or detect_version(None) or policy.version
    # A new document has not been approved just because the last one was.
    policy.status = "needs_review"
    policy.approved_by = None
    policy.approved_at = None

    db.add(
        PolicyVersion(
            organization_id=organization_id,
            policy_id=policy.id,
            file_id=file_record.id,
            version=policy.version,
            status="current",
        )
    )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.policy.version_replaced",
        object_type="policy",
        object_id=str(policy.id),
        before_state={"file_id": str(previous_file_id) if previous_file_id else None},
        after_state={"file_id": str(file_record.id), "version": policy.version},
    )
    return policy


async def approve_policy(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    policy: Policy,
    actor_user_id: uuid.UUID,
    note: str | None = None,
) -> Policy:
    """Record that a person approved this policy.

    Only a person reaches this. Automatic detection never sets `approved`,
    because approval is an organizational act and a product that performs
    it on the customer's behalf is forging a record.
    """
    now = datetime.now(UTC)
    before = policy.status
    policy.status = "approved"
    policy.approved_by = actor_user_id
    policy.approved_at = now
    if policy.effective_date is None:
        policy.effective_date = now
    if policy.next_review_at is None and policy.review_frequency_months:
        policy.next_review_at = now + timedelta(days=30 * policy.review_frequency_months)

    current = (
        await db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.id, PolicyVersion.status == "current"
            )
        )
    ).scalars().first()
    if current is not None:
        current.approved_at = now

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.policy.approved",
        object_type="policy",
        object_id=str(policy.id),
        before_state={"status": before},
        after_state={
            "status": "approved",
            "version": policy.version,
            "file_id": str(policy.file_id) if policy.file_id else None,
            "note": note,
        },
    )
    return policy


def review_state(policy: Policy, *, now: datetime | None = None) -> str:
    """Whether this policy's review is due, overdue, or neither.

    Derived rather than stored so it cannot go stale against the calendar.
    Note what this does *not* do: an overdue review never marks a control
    failed. Whether a lapsed review breaks a requirement is the
    framework's call, not a side effect of a date passing.
    """
    if policy.status in ("retired", "superseded"):
        return "not_applicable"
    if policy.next_review_at is None:
        return "not_scheduled"
    moment = now or datetime.now(UTC)
    due = policy.next_review_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    if due < moment:
        return "overdue"
    if due - moment <= timedelta(days=30):
        return "due_soon"
    return "scheduled"


def missing_governance(policy: Policy) -> list[str]:
    """What a person still has to tell us about this policy.

    The list the UI turns into "Complete setup". Empty means the record is
    complete, which is the only state where "Approved" means anything.
    """
    missing: list[str] = []
    if policy.owner_id is None:
        missing.append("Owner")
    if not policy.version:
        missing.append("Version")
    if policy.status != "approved":
        missing.append("Approval")
    if policy.next_review_at is None:
        missing.append("Next review date")
    return missing


async def backfill_organization(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    limit: int = 200,
) -> dict[str, int]:
    """Create governance records for policy documents already uploaded.

    Detection was added after customers had libraries of policies, so
    without this every existing tenant sees "no policies" beside ten
    policy documents. Idempotent: it looks up each document's existing
    record first, so running it repeatedly changes nothing.
    """
    files = list(
        (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == organization_id,
                    File.processing_status == "ready",
                    File.document_type.is_not(None),
                )
                .order_by(File.created_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    counts = {"created": 0, "linked": 0, "skipped": 0}
    for file_record in files:
        before = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Policy)
                    .where(Policy.organization_id == organization_id)
                )
            ).scalar_one()
        )
        policy = await ensure_policy_for_document(
            db,
            organization_id=organization_id,
            file_record=file_record,
            actor_user_id=actor_user_id,
        )
        if policy is None:
            counts["skipped"] += 1
            continue
        after = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Policy)
                    .where(Policy.organization_id == organization_id)
                )
            ).scalar_one()
        )
        counts["created" if after > before else "linked"] += 1

    await db.commit()
    if counts["created"]:
        logger.info("Policy backfill for %s: %s", organization_id, counts)
    return counts


__all__ = [
    "POLICY_STATUSES",
    "approve_policy",
    "backfill_organization",
    "days_until_review",
    "detect_version",
    "ensure_policy_for_document",
    "looks_like_a_policy",
    "missing_governance",
    "promote_document_to_current_version",
    "review_state",
]


def days_until_review(policy: Policy, *, now: datetime | None = None) -> int | None:
    """Whole days until this policy's review, or None if unscheduled.

    Computed here rather than in the browser: a `Date.now()` inside a
    render is impure and produces a different answer on every paint.
    Negative when overdue, which is the honest number.
    """
    if policy.next_review_at is None:
        return None
    due = policy.next_review_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    delta = due - (now or datetime.now(UTC))
    return int(delta.total_seconds() // 86400)
