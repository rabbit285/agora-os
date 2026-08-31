"""The audit trail, as a compliance manager reads it.

The stored event is machine-shaped and has to be: a stable action name, a
UUID, and the before/after state as JSON. That is what makes it
greppable, filterable and provable. It is also unreadable — the screen
was showing `compliance.control.assessed`, `after {"status":"pass"}` and
a bare UUID, which asks the reader to do the translation the product
should have done for them.

So the stored row is untouched and this module translates it, once,
server-side. Every surface that shows an audit event reads the same
words, the same actor and the same link.

Four things get resolved here:

- **The title.** `compliance.control.assessed` reads as "Control
  assessment changed". An action with no phrasing is skipped rather than
  shown raw — a feed may be incomplete, never leak an internal name.
- **The entity.** A UUID becomes "Monitor AI systems in production", with
  the route that opens it. A record that has since been deleted says so.
- **The actor.** Who or what did this: a person, Veyntra's AI, Veyntra's
  own rules, or an integration. Never fabricated — an event with no
  recorded actor says the actor is unavailable.
- **The change.** `{"status": "pass"}` becomes "Assessment: Needs review
  → Passed".

The raw fields still travel with the view, for the technical drawer. The
point is that they stop being the only thing on offer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.control_assessment import ASSESSMENT_LABELS
from app.compliance.models import (
    DPIA,
    DSAR,
    AIIncident,
    AISystem,
    Audit,
    ComplianceGap,
    Control,
    Evidence,
    EvidenceSuggestion,
    Framework,
    Policy,
    Questionnaire,
    Requirement,
    SecurityReview,
    Vendor,
)
from app.core.models import File, Organization, Task
from app.identity.models import User
from app.knowledge.documents import hrefs_for_files, readable_title

# --- who did it -------------------------------------------------------

# Work a model performed. Named per action rather than inferred, because
# the difference between "a model proposed this" and "our rules derived
# this" is exactly what an auditor is reading the trail to find out, and
# guessing it from whether a user id happens to be recorded gets it
# wrong in both directions.
AI_ACTIONS = frozenset(
    {
        "compliance.evidence.suggestions_generated",
        "compliance.evidence.suggestion_auto_approved",
        "compliance.gap.remediation_generated",
        "compliance.gap.remediation_updated",
        "compliance.policy.detected",
        "core.file.version_candidate_detected",
        "compliance.questionnaire_answer.ai_suggested",
        "compliance.dpia.created_from_ai_system",
    }
)

# Work Veyntra's own rules performed, with no model involved.
# `compliance.framework.assessed` is deliberately here and not in
# AI_ACTIONS: assessment in this product is deterministic rules over
# declared facts, never a model call, and calling it AI would
# misrepresent how the number was reached.
SYSTEM_ACTIONS = frozenset(
    {
        "compliance.framework.assessed",
        "compliance.gap.created",
        "compliance.gap.resolved",
        "compliance.gap.control_reassessed",
        "compliance.gap.evidence_detected",
        "compliance.gap.task_created",
        "compliance.control.reassessment_flagged",
    }
)

ACTOR_KINDS = ("person", "ai", "system", "integration", "unknown")

ACTOR_NAMES = {
    "ai": "Veyntra AI",
    "system": "Veyntra System",
    "unknown": "Actor unavailable",
}


def actor_kind_for(action: str, has_user: bool) -> str:
    """Which kind of actor performed this event."""
    if action in AI_ACTIONS:
        return "ai"
    if action in SYSTEM_ACTIONS:
        return "system"
    if action.startswith("integrations."):
        return "integration"
    return "person" if has_user else "unknown"


def _short_name(full_name: str | None, email: str | None) -> str:
    """"Zach Warren" reads as "Zach W." — enough to know who, short
    enough for a feed. An account with no name falls back to the local
    part of its email rather than to a UUID."""
    name = (full_name or "").strip()
    if name:
        parts = name.split()
        if len(parts) == 1:
            return parts[0][:60]
        return f"{parts[0]} {parts[-1][:1].upper()}."[:60]
    if email:
        return email.split("@")[0][:60]
    return "Actor unavailable"


# --- what happened ----------------------------------------------------

# Every action this organization can record, as a sentence. Kept
# exhaustive rather than pattern-derived: "gap remediation updated" is
# what a machine name humanizes to, and it is not what happened.
TITLES: dict[str, str] = {
    # Controls and frameworks
    "compliance.control.assessed": "Control assessment recorded",
    "compliance.control.created": "Control created",
    "compliance.control.updated": "Control updated",
    "compliance.control.reassessment_flagged": "Control flagged for reassessment",
    "compliance.framework.assessed": "Framework reassessed",
    "compliance.framework.activated": "Framework adopted",
    "compliance.framework.deactivated": "Framework withdrawn",
    "compliance.framework.created": "Custom framework created",
    "compliance.company_facts.declared": "Company facts declared",
    # Gaps and remediation
    "compliance.gap.created": "Gap identified",
    "compliance.gap.remediation_generated": "Remediation plan drafted",
    "compliance.gap.remediation_updated": "Remediation plan updated",
    "compliance.gap.task_created": "Remediation task raised",
    "compliance.gap.evidence_detected": "New evidence detected",
    "compliance.gap.control_reassessed": "Control reassessed",
    "compliance.gap.resolved": "Gap resolved",
    # Documents and evidence
    "core.file.upload_requested": "Document uploaded",
    "compliance.questionnaire.archived": "Questionnaire archived",
    "compliance.questionnaire.restored": "Questionnaire restored",
    "compliance.questionnaire.deleted": "Questionnaire permanently deleted",
    "compliance.audit.archived": "Audit archived",
    "compliance.audit.restored": "Audit restored",
    "compliance.audit.deleted": "Audit permanently deleted",
    "core.file.version_added": "New version of a document accepted",
    "core.file.version_candidate_detected": "Possible new version detected",
    "core.file.kept_as_separate_document": "Kept as a separate document",
    "compliance.evidence.suggestions_generated": "Document read for evidence",
    "compliance.evidence.suggestion_approved": "Evidence mapping approved",
    "compliance.evidence.suggestion_auto_approved": "Evidence mapped automatically",
    "compliance.evidence.suggestion_rejected": "Evidence mapping rejected",
    "compliance.evidence.created": "Evidence attached",
    # Policies
    "compliance.policy.detected": "Policy found in a document",
    "compliance.policy.created": "Policy record created",
    "compliance.policy.governance_updated": "Policy governance updated",
    "compliance.policy.approved": "Policy approved",
    "compliance.policy.status_changed": "Policy status changed",
    "compliance.policy.version_replaced": "Policy document replaced",
    "compliance.policy.new_version_detected": "Newer policy document detected",
    # Tasks
    "core.task.created": "Task created",
    "core.task.status_changed": "Task status changed",
    "core.task.checklist_updated": "Remediation checklist updated",
    "core.task.assigned": "Task owner assigned",
    "core.task.commented": "Comment added",
    "core.task.evidence_attached": "Evidence attached to task",
    # Privacy
    "compliance.dsar.received": "Data subject request received",
    "compliance.dsar.status_changed": "Data subject request updated",
    "compliance.dpia.created": "DPIA created",
    "compliance.dpia.created_from_ai_system": "DPIA drafted for an AI system",
    "compliance.data_transfer.created": "International transfer recorded",
    # AI systems
    "compliance.ai_system.registered": "AI system registered",
    "compliance.ai_incident.created": "AI incident logged",
    # Vendors and assessments
    "compliance.vendor.created": "Vendor added",
    "compliance.security_review.started": "Security review started",
    "compliance.security_review.created": "Customer security review opened",
    "compliance.security_review.questionnaire_linked": "Questionnaire added to security review",
    "compliance.security_review.status_changed": "Security review status changed",
    "compliance.security_review.archived": "Security review archived",
    "compliance.security_review.restored": "Security review restored",
    "compliance.security_review.customer_set": "Security review customer named",
    "compliance.questionnaire.renamed": "Questionnaire renamed",
    "compliance.questionnaire.customer_set": "Questionnaire customer named",
    "compliance.security_review.synced": "Security review updated",
    "compliance.questionnaire_question.added": "Questionnaire question added",
    "compliance.questionnaire_answer.ai_suggested": "Answer drafted by Veyntra AI",
    "compliance.questionnaire_answer.status_changed": "Questionnaire answer updated",
    "compliance.audit_finding.created": "Audit finding raised",
    "compliance.audit_finding.status_changed": "Audit finding updated",
    # Trust Center
    "trust_center.item.upserted": "Trust Center entry updated",
    "trust_center.evidence_request.created": "Trust Center evidence requested",
    # Access
    "auth.login": "Signed in",
    "auth.signup": "Organization created",
    "auth.logout": "Signed out",
    "auth.password_changed": "Password changed",
    "auth.mfa_enabled": "Two-factor authentication enabled",
    # Security and platform
    "security.incident.created": "Security incident logged",
    "integrations.webhook.received": "Webhook received",
}

# Which filter chip an action belongs under. First matching prefix wins,
# so the specific entries have to precede the general ones.
CATEGORY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("compliance.gap.", "gaps"),
    ("compliance.evidence.", "evidence"),
    ("core.file.", "evidence"),
    ("compliance.policy.", "policies"),
    ("compliance.dsar", "privacy"),
    ("compliance.dpia", "privacy"),
    ("compliance.data_transfer", "privacy"),
    ("compliance.ai_system", "ai_systems"),
    ("compliance.ai_incident", "ai_systems"),
    ("compliance.vendor", "vendors"),
    ("compliance.security_review", "vendors"),
    ("compliance.questionnaire", "vendors"),
    ("compliance.audit_finding", "reviews"),
    ("trust_center.", "vendors"),
    ("core.task.", "gaps"),
    ("compliance.", "compliance"),
    ("auth.", "security"),
    ("security.", "security"),
    ("billing.", "billing"),
    ("integrations.", "integrations"),
)

CATEGORY_LABELS = {
    "compliance": "Compliance",
    "evidence": "Evidence & documents",
    "reviews": "Reviews & approvals",
    "gaps": "Gaps & remediation",
    "ai_systems": "AI systems",
    "privacy": "Privacy",
    "vendors": "Vendors",
    "policies": "Policies",
    "security": "Security",
    "billing": "Billing",
    "integrations": "Integrations",
    "other": "Other",
}


def category_for(action: str) -> str:
    for prefix, category in CATEGORY_PREFIXES:
        if action.startswith(prefix):
            return category
    return "other"


# --- what changed -----------------------------------------------------

FIELD_LABELS: dict[str, str] = {
    "status": "Status",
    "owner": "Owner",
    "requirement": "Requirement",
    "checklist_items": "Checklist",
    "required_evidence": "Required evidence",
    "evidence_reviewed": "Evidence reviewed",
    "requirements_evaluated": "Requirements evaluated",
    "satisfied": "Satisfied",
    "needs_review": "Awaiting review",
    "gaps": "Gaps",
    "filename": "Document",
    "severity": "Severity",
    "confidence": "Confidence",
    "control": "Control",
    "framework": "Framework",
    "title": "Title",
    "reason": "Reason",
    "notes": "Note",
    "closed_by": "Closed by",
    "assignee": "Assignee",
    "version": "Version",
    "done": "Completed",
    "total": "Total steps",
}

# Fields that are the event's explanation rather than a changed value.
# Surfaced on their own, because "why" is the question a human override
# exists to answer.
REASON_FIELDS = ("notes", "reason", "rationale", "justification")

# Internal bookkeeping nobody reading the trail needs to see.
HIDDEN_FIELDS = frozenset({"id", "organization_id", "actor_user_id", "correlation_id"})


def _is_identifier_field(key: str) -> bool:
    """Any field whose value is a key rather than a fact.

    The after-state of a real event carries `control_id`,
    `evidence_id`, `requirement_id` and friends. Rendering those put
    `Control id: eec03b4e-62a2-4e7b-8362-0cfaac423d40` back on the
    timeline through the side door, which is the thing this redesign
    exists to stop. They stay in the drawer, where an id is what the
    reader came for.
    """
    return key in HIDDEN_FIELDS or key.endswith("_id") or key.endswith("_ids")

# Values with an established word elsewhere in the product, so the audit
# trail and the screens agree.
VALUE_LABELS: dict[str, str] = {
    **ASSESSMENT_LABELS,
    "pass": "Passed",
    "fail": "Failed",
    "partial": "Partially implemented",
    "not_assessed": "Not assessed",
    "open": "Open",
    "in_progress": "In progress",
    "done": "Done",
    "cancelled": "Cancelled",
    "resolved": "Resolved",
    "gap_resolved": "the gap being resolved",
    "evidence_found": "new evidence",
    "needs_review": "Needs review",
    "approved": "Approved",
    "draft": "Draft",
    "superseded": "Superseded",
    "retired": "Retired",
    "review_due": "Review due",
}


def format_value(value: Any) -> str:
    """One field value, as a person would write it."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int | float):
        return f"{value:,}" if isinstance(value, int) else f"{value:g}"
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            # A checklist, not a list of words. "2 fields, 2 fields,
            # 2 fields" is what naive formatting produced; what the
            # reader wants is how much of it is done.
            done = sum(1 for item in value if item.get("done"))
            noun = "step" if len(value) == 1 else "steps"
            return f"{done} of {len(value)} {noun} complete"
        return ", ".join(format_value(item) for item in value[:6]) or "—"
    if isinstance(value, dict):
        # Nested structure has no readable one-line form. The drawer has
        # the JSON; the card says how much there is rather than pasting
        # a brace-soup into the timeline.
        return f"{len(value)} field{'' if len(value) == 1 else 's'}"
    text = str(value)
    return VALUE_LABELS.get(text, text.replace("_", " ").strip() or "—")


@dataclass(frozen=True)
class AuditChange:
    """One field that moved, or one fact the event recorded.

    `before` is None where the event only recorded a new value — most
    audit writes do, and inventing a previous value to fill the arrow
    would be a claim the record does not make.
    """

    label: str
    before: str | None
    after: str


def summarize_change(
    action: str, before_state: dict[str, Any] | None, after_state: dict[str, Any] | None
) -> list[AuditChange]:
    """Turn the stored JSON into lines a person can read.

    Every key in `after_state` becomes a line, paired with its previous
    value where one was recorded. Unknown keys are humanized rather than
    dropped: a field this module has not been taught about is still the
    customer's data, and hiding it would make the trail less complete
    than the JSON it replaced.
    """
    after = after_state or {}
    before = before_state or {}
    changes: list[AuditChange] = []

    for key, value in after.items():
        if _is_identifier_field(key) or key in REASON_FIELDS:
            continue
        label = FIELD_LABELS.get(key, key.replace("_", " ").capitalize())
        previous = before.get(key)
        changes.append(
            AuditChange(
                label=label,
                before=format_value(previous) if key in before else None,
                after=format_value(value),
            )
        )

    # A before-state with keys the after-state dropped is still a change.
    for key, value in before.items():
        if _is_identifier_field(key) or key in REASON_FIELDS or key in after:
            continue
        label = FIELD_LABELS.get(key, key.replace("_", " ").capitalize())
        changes.append(AuditChange(label=label, before=format_value(value), after="—"))

    return changes


def reason_from(after_state: dict[str, Any] | None) -> str | None:
    """The person's own words, where the event recorded them."""
    state = after_state or {}
    for key in REASON_FIELDS:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:1000]
    return None


# --- what it happened to ----------------------------------------------

# object_type -> (model, kind shown to the reader, route template).
# A route of None means the record has no page of its own; the name is
# still resolved, so the reader knows what was affected.
ENTITY_SOURCES: dict[str, tuple[type[Any], str, str | None]] = {
    "control": (Control, "Control", "/compliance/controls/{id}"),
    "framework": (Framework, "Framework", "/compliance/frameworks/{id}"),
    "policy": (Policy, "Policy", "/compliance/policies/{id}"),
    "ai_system": (AISystem, "AI system", "/compliance/ai-systems/{id}"),
    "ai_incident": (AIIncident, "AI incident", "/compliance/ai-incidents/{id}"),
    "task": (Task, "Task", "/tasks/{id}"),
    "dsar": (DSAR, "Data subject request", "/compliance/dsars/{id}"),
    "dpia": (DPIA, "DPIA", "/compliance/dpias/{id}"),
    "vendor": (Vendor, "Vendor", "/compliance/vendors/{id}"),
    "audit": (Audit, "Assessment", "/compliance/audits/{id}"),
    "questionnaire": (Questionnaire, "Questionnaire", "/compliance/questionnaires/{id}"),
    "security_review": (SecurityReview, "Security review", "/compliance/security-reviews/{id}"),
    "requirement": (Requirement, "Requirement", None),
    "evidence": (Evidence, "Evidence", None),
    "organization": (Organization, "Organization", None),
    "user": (User, "User", None),
}

# Tried in order. Models name their principal column differently and
# guessing per model is how a rename becomes a blank row.
LABEL_COLUMNS = (
    "title",
    "name",
    "summary",
    "full_name",
    "original_filename",
    "reference_code",
    "subject_email",
    "email",
)


def _label_of(row: Any) -> str | None:
    for column in LABEL_COLUMNS:
        value = getattr(row, column, None)
        if isinstance(value, str) and value.strip():
            return _clean_label(value)
    return None


def _clean_label(value: str) -> str:
    """A gap summary often opens by quoting the requirement it is about,
    so the name arrives as `'Restrict access to personal data…`. The
    stray quote is punctuation from another sentence, not part of the
    name."""
    return value.strip().strip("‘’“”\"'")[:200] or value.strip()[:200]


@dataclass
class ResolvedEntity:
    kind: str
    label: str
    href: str | None = None
    # False when the record has been deleted, or was never resolvable.
    # The reader is told which rather than shown a UUID.
    available: bool = True


@dataclass
class AuditEventView:
    """One audit event, ready to render.

    The raw fields are still here — `action`, `object_id`, both states —
    for the technical drawer and for anyone exporting the trail. They are
    simply no longer the only thing the screen can show.
    """

    id: uuid.UUID
    action: str
    title: str
    category: str
    category_label: str
    created_at: Any
    entity: ResolvedEntity | None
    actor_name: str
    actor_kind: str
    actor_email: str | None
    changes: list[AuditChange] = field(default_factory=list)
    reason: str | None = None
    object_type: str = ""
    object_id: str | None = None
    actor_user_id: uuid.UUID | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    correlation_id: uuid.UUID | None = None


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


async def _resolve_entities(
    db: AsyncSession, *, organization_id: uuid.UUID, events: list[AuditEvent]
) -> dict[tuple[str, str], ResolvedEntity]:
    """Every event's subject, named, in one query per type.

    Batched by object type because a page of two hundred events would
    otherwise be two hundred round trips — and this screen exists to be
    scanned.
    """
    wanted: dict[str, set[uuid.UUID]] = {}
    for event in events:
        identifier = _as_uuid(event.object_id)
        if identifier is not None:
            wanted.setdefault(event.object_type, set()).add(identifier)

    resolved: dict[tuple[str, str], ResolvedEntity] = {}

    for object_type, ids in wanted.items():
        # --- the ones with their own shape ---------------------------
        if object_type == "file":
            files = (
                (await db.execute(select(File).where(File.id.in_(ids))))
                .scalars()
                .all()
            )
            hrefs = await hrefs_for_files(
                db, organization_id=organization_id, file_ids=[f.id for f in files]
            )
            for file_record in files:
                resolved[(object_type, str(file_record.id))] = ResolvedEntity(
                    kind="Document",
                    label=readable_title(file_record.original_filename),
                    href=hrefs.get(file_record.id),
                )
            continue

        if object_type == "compliance_gap":
            rows = (
                (
                    await db.execute(
                        select(ComplianceGap, Requirement, Framework)
                        .outerjoin(Requirement, Requirement.id == ComplianceGap.requirement_id)
                        .outerjoin(Framework, Framework.id == ComplianceGap.framework_id)
                        .where(ComplianceGap.id.in_(ids))
                    )
                ).all()
            )
            for gap, requirement, framework in rows:
                # A gap has no page of its own; it is read on the
                # framework screen, next to the requirement it is about.
                label = _clean_label(
                    gap.summary
                    or (
                        f"{requirement.reference_code} {requirement.title}"
                        if requirement
                        else "Compliance gap"
                    )
                )
                resolved[(object_type, str(gap.id))] = ResolvedEntity(
                    kind="Gap",
                    label=label,
                    href=f"/compliance/frameworks/{framework.id}" if framework else None,
                )
            continue

        if object_type == "evidence_suggestion":
            rows = (
                (
                    await db.execute(
                        select(EvidenceSuggestion, Control)
                        .outerjoin(Control, Control.id == EvidenceSuggestion.control_id)
                        .where(EvidenceSuggestion.id.in_(ids))
                    )
                ).all()
            )
            for suggestion, control in rows:
                # The mapping is about a control; that is the record a
                # reader following this event wants to open.
                resolved[(object_type, str(suggestion.id))] = ResolvedEntity(
                    kind="Evidence mapping",
                    label=control.title if control else "Evidence mapping",
                    href=f"/compliance/controls/{control.id}" if control else None,
                )
            continue

        # --- everything table-driven ---------------------------------
        source = ENTITY_SOURCES.get(object_type)
        if source is None:
            continue
        model, kind, route = source
        rows = (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()
        for row in rows:
            label = _label_of(row)
            if label is None:
                continue
            resolved[(object_type, str(row.id))] = ResolvedEntity(
                kind=kind,
                label=label,
                href=route.format(id=row.id) if route else None,
            )

    return resolved


async def _resolve_actors(
    db: AsyncSession, events: list[AuditEvent]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    ids = {event.actor_user_id for event in events if event.actor_user_id}
    if not ids:
        return {}
    users = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {
        user.id: (
            _short_name(getattr(user, "full_name", None), getattr(user, "email", None)),
            getattr(user, "email", None),
        )
        for user in users
    }


def _entity_kind_fallback(object_type: str) -> str:
    source = ENTITY_SOURCES.get(object_type)
    if source is not None:
        return source[1]
    return object_type.replace("_", " ").capitalize() or "Record"


async def build_views(
    db: AsyncSession, *, organization_id: uuid.UUID, events: list[AuditEvent]
) -> list[AuditEventView]:
    """Every event on this page, resolved for reading."""
    if not events:
        return []

    entities = await _resolve_entities(
        db, organization_id=organization_id, events=events
    )
    actors = await _resolve_actors(db, events)

    views: list[AuditEventView] = []
    for event in events:
        kind = actor_kind_for(event.action, event.actor_user_id is not None)
        if kind == "person":
            name, email = actors.get(event.actor_user_id or uuid.UUID(int=0), (None, None))
            actor_name = name or "Actor unavailable"
            actor_email = email
        else:
            actor_name = ACTOR_NAMES.get(kind, "Veyntra System")
            actor_email = None
            if kind == "integration":
                actor_name = "Integration"

        entity = entities.get((event.object_type, event.object_id or ""))
        if entity is None and event.object_id:
            # Resolved to nothing: either the record was deleted, or its
            # type has no lookup here. Saying so beats printing the UUID
            # the reader cannot do anything with.
            entity = ResolvedEntity(
                kind=_entity_kind_fallback(event.object_type),
                label=f"Deleted {_entity_kind_fallback(event.object_type).lower()}",
                href=None,
                available=False,
            )

        category = category_for(event.action)
        views.append(
            AuditEventView(
                id=event.id,
                action=event.action,
                title=TITLES.get(event.action)
                or event.action.split(".")[-1].replace("_", " ").capitalize(),
                category=category,
                category_label=CATEGORY_LABELS.get(category, "Other"),
                created_at=event.created_at,
                entity=entity,
                actor_name=actor_name,
                actor_kind=kind,
                actor_email=actor_email,
                changes=summarize_change(event.action, event.before_state, event.after_state),
                reason=reason_from(event.after_state),
                object_type=event.object_type,
                object_id=event.object_id,
                actor_user_id=event.actor_user_id,
                before_state=event.before_state,
                after_state=event.after_state,
                correlation_id=event.correlation_id,
            )
        )
    return views


__all__ = [
    "AI_ACTIONS",
    "ACTOR_KINDS",
    "CATEGORY_LABELS",
    "SYSTEM_ACTIONS",
    "TITLES",
    "AuditChange",
    "AuditEventView",
    "ResolvedEntity",
    "actor_kind_for",
    "build_views",
    "category_for",
    "format_value",
    "reason_from",
    "summarize_change",
]
