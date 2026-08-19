"""Continuous monitoring: the connector catalog and evidence events.

Compliance decays. A control that passed in March fails in June because
someone turned off branch protection, and nobody finds out until the next
audit. Continuous monitoring is the answer to that, and its shape is:

    a connector observes something
        -> an EvidenceEvent is recorded
        -> the control it bears on is marked for reassessment
        -> the next assessment reflects reality

**Nothing here pretends to be connected.** Every connector in the
catalog reports its real state, and right now that is `coming_soon` for
all of them: the OAuth plumbing for GitHub, Google, Microsoft and Slack
exists elsewhere in this repository, but none of it produces compliance
evidence yet, and a catalog that implied otherwise would be the single
most damaging thing this module could ship. A customer who believes their
GitHub settings are being watched, and is wrong, is worse off than one
who knows they are not.

The ingestion path below is real and tested. It is exercised directly
rather than through a live connector, which is the honest way to build
the receiving end before the sending end exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Control, EvidenceEvent

# What a connector can say. Deliberately small: each maps to something
# the assessment can actually act on, rather than a general-purpose event
# bus nobody downstream understands.
EVENT_TYPES = (
    # A configuration we depend on is still in place.
    "control_configuration_confirmed",
    # A configuration we depend on changed in a way that weakens it.
    "control_configuration_weakened",
    # A document or artifact we treat as evidence was updated at source.
    "evidence_updated",
    # The connector could not observe what it was asked to. Recorded
    # rather than silently skipped: "we did not look" and "we looked and
    # it was fine" must never be indistinguishable.
    "observation_failed",
)

# Events that call the current assessment into question. A confirmation
# does not — re-running an assessment because nothing changed is churn,
# and would bury the events that matter.
REASSESSMENT_TRIGGERS = frozenset(
    {"control_configuration_weakened", "evidence_updated", "observation_failed"}
)


@dataclass(frozen=True)
class Connector:
    key: str
    name: str
    category: str
    # available | coming_soon
    status: str
    # What it would observe, stated concretely. A catalog entry that says
    # "improves your compliance posture" tells a buyer nothing about
    # whether it is worth connecting.
    observes: str


CONNECTORS: tuple[Connector, ...] = (
    Connector(
        key="github",
        name="GitHub",
        category="Engineering",
        status="coming_soon",
        observes="Branch protection, required reviews, and who has admin access to your repositories.",
    ),
    Connector(
        key="microsoft_365",
        name="Microsoft 365",
        category="Identity & productivity",
        status="coming_soon",
        observes="MFA enforcement, conditional access policies, and admin role assignments.",
    ),
    Connector(
        key="google_workspace",
        name="Google Workspace",
        category="Identity & productivity",
        status="coming_soon",
        observes="Two-step verification coverage, external sharing settings, and admin roles.",
    ),
    Connector(
        key="sharepoint",
        name="SharePoint",
        category="Document management",
        status="coming_soon",
        observes="Policy documents and their revision history, as a live evidence source.",
    ),
    Connector(
        key="aws",
        name="AWS",
        category="Cloud",
        status="coming_soon",
        observes="Encryption at rest, logging configuration, and IAM policy changes.",
    ),
    Connector(
        key="azure",
        name="Azure",
        category="Cloud",
        status="coming_soon",
        observes="Encryption, diagnostic settings, and role assignments.",
    ),
    Connector(
        key="gcp",
        name="Google Cloud",
        category="Cloud",
        status="coming_soon",
        observes="Encryption, audit logging, and IAM bindings.",
    ),
    Connector(
        key="jira",
        name="Jira",
        category="Engineering",
        status="coming_soon",
        observes="Whether remediation work is actually being tracked and closed.",
    ),
    Connector(
        key="slack",
        name="Slack",
        category="Communication",
        status="coming_soon",
        observes="Incident channel activity, as a signal for the breach response control.",
    ),
    Connector(
        key="microsoft_teams",
        name="Microsoft Teams",
        category="Communication",
        status="coming_soon",
        observes="Incident channel activity, as a signal for the breach response control.",
    ),
    Connector(
        key="hr_system",
        name="HR system",
        category="People",
        status="coming_soon",
        observes="Joiners and leavers, so access reviews and training records stay current.",
    ),
    Connector(
        key="identity_provider",
        name="Identity provider",
        category="Identity & productivity",
        status="coming_soon",
        observes="SSO enforcement, MFA coverage, and deprovisioning of departed staff.",
    ),
    Connector(
        key="security_platform",
        name="Security platform",
        category="Security",
        status="coming_soon",
        observes="Vulnerability findings and endpoint coverage.",
    ),
)

CONNECTORS_BY_KEY = {connector.key: connector for connector in CONNECTORS}


class UnknownConnectorError(Exception):
    """An event arrived claiming a source we do not have."""


async def record_evidence_event(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    source: str,
    event_type: str,
    summary: str,
    control_id: uuid.UUID | None = None,
    external_id: str | None = None,
    payload: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> EvidenceEvent:
    """Record an observation, and mark what it calls into question.

    The receiving end of continuous monitoring. Deliberately does not
    change any control's status: an observation is evidence that the
    position may have moved, not a new position. It flags the control for
    reassessment and lets the deterministic assessment decide — which
    keeps one rule in one place rather than letting connectors quietly
    grade controls by a second standard.

    Never deletes or overwrites existing evidence. A connector reporting
    that something changed must not be able to destroy the record of what
    was true before.
    """
    if source not in CONNECTORS_BY_KEY:
        raise UnknownConnectorError(f"No connector named {source!r}.")
    if event_type not in EVENT_TYPES:
        raise UnknownConnectorError(f"Unsupported event type {event_type!r}.")

    control: Control | None = None
    if control_id is not None:
        control = await db.get(Control, control_id)
        if control is None or control.organization_id != organization_id:
            control = None
            control_id = None

    event = EvidenceEvent(
        organization_id=organization_id,
        source=source,
        event_type=event_type,
        summary=summary[:500],
        control_id=control_id,
        external_id=external_id,
        payload=payload or {},
        observed_at=datetime.now(UTC),
        triggered_reassessment=False,
    )
    db.add(event)
    await db.flush()

    if control is not None and event_type in REASSESSMENT_TRIGGERS:
        control.needs_reassessment = True
        event.triggered_reassessment = True

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.evidence_event.recorded",
        object_type="evidence_event",
        object_id=str(event.id),
        after_state={
            "source": source,
            "event_type": event_type,
            "control_id": str(control_id) if control_id else None,
            "triggered_reassessment": event.triggered_reassessment,
        },
    )
    return event


async def list_evidence_events(
    db: AsyncSession, *, organization_id: uuid.UUID, limit: int = 50
) -> list[EvidenceEvent]:
    return list(
        (
            await db.execute(
                select(EvidenceEvent)
                .where(EvidenceEvent.organization_id == organization_id)
                .order_by(EvidenceEvent.observed_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


__all__ = [
    "CONNECTORS",
    "CONNECTORS_BY_KEY",
    "EVENT_TYPES",
    "REASSESSMENT_TRIGGERS",
    "Connector",
    "UnknownConnectorError",
    "list_evidence_events",
    "record_evidence_event",
]
