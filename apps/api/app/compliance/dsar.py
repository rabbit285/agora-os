"""Data subject access requests: verification, discovery, and export.

The security property here is the whole point, and it runs the opposite
way to most of this module. Everywhere else the risk is claiming
compliance we cannot support. Here the risk is *doing what we are asked*:
an access request is a request to hand over everything we hold about a
named person, and answering one without establishing who is asking is how
a controller discloses one person's data to another. The request is the
attack.

So `generate_export` refuses unless the request is verified, and it
refuses in the service rather than the router — a second endpoint added
later, or a background job, must hit the same wall. Article 12(6) exists
precisely so a controller can demand proof before answering.

Discovery no longer lives here. It moved to `dsar_discovery`, which
searches only the scope a person confirmed and reports honestly on
everything it could not reach.

What was removed from this module mattered: it searched
`support_customers`, `support_tickets`, `sales_contacts` and
`sales_leads` — tables belonging to product modules Veyntra no longer
ships — and reported "0 matches" for each. A case worker reading that
zero would sign a response saying no data was found, on the strength of
a query against systems this product does not operate. That is worse
than not looking, because it looks like having looked.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import DSAR


class DsarVerificationRequired(Exception):
    """Raised when an action that discloses personal data is attempted on
    a request whose requester has not been verified."""


async def verify_identity(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    method: str,
    verified: bool,
    actor_user_id: uuid.UUID | None,
    notes: str | None = None,
) -> DSAR:
    """Record the outcome of identity verification.

    Both outcomes are recorded. A failed verification is a fact about the
    request that the audit trail needs — "we refused this one, and why" is
    as important to be able to show as a completed response.
    """
    dsar.verification_status = "verified" if verified else "failed"
    dsar.verification_method = method
    # Kept on both outcomes. Why a verification failed is exactly what a
    # second attempt, or a complaint, needs to be able to read.
    dsar.verification_notes = (notes or '').strip() or None
    dsar.verified_at = datetime.now(UTC) if verified else None
    dsar.verified_by = actor_user_id if verified else None

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.identity_verified"
        if verified
        else "compliance.dsar.identity_verification_failed",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={
            "verification_status": dsar.verification_status,
            "method": method,
            # The note itself is not copied into the audit trail: it can
            # describe how a person proved who they were, which is not
            # something to duplicate into a second store.
            "notes_recorded": bool(dsar.verification_notes),
        },
    )
    return dsar


def build_export_payload(dsar: DSAR) -> str:
    """The response package, as text.

    Carries the coverage note and the verification record with it, so a
    package separated from this system still says how it was produced and
    what it did not cover.
    """
    # Narrowed explicitly: the column is JSON, so its value type is
    # `object` and the loop below would otherwise be unchecked.
    findings: dict[str, Any] = dict(dsar.discovery_findings or {})
    sources: list[dict[str, Any]] = list(findings.get("sources") or [])
    lines = [
        "DATA SUBJECT ACCESS REQUEST — RESPONSE PACKAGE",
        "",
        f"Data subject: {dsar.requester_name} <{dsar.requester_email}>",
        f"Request type: {dsar.request_type}",
        f"Received: {dsar.created_at.isoformat() if dsar.created_at else 'unknown'}",
        f"Identity verification: {dsar.verification_status}"
        + (f" via {dsar.verification_method}" if dsar.verification_method else ""),
        f"Verified at: {dsar.verified_at.isoformat() if dsar.verified_at else 'not verified'}",
        "",
        "SOURCES SEARCHED",
    ]
    for source in sources:
        lines.append(f"  - {source['source']}: {source['matches']} match(es)")
    lines += [
        "",
        "COVERAGE",
        f"  {findings.get('coverage_note', 'No discovery has been run for this request.')}",
        "",
        "RECORD REFERENCES",
        json.dumps(sources, indent=2),
    ]
    return "\n".join(lines)


async def generate_export(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    actor_user_id: uuid.UUID | None,
) -> tuple[bytes, str]:
    """Produce the response package.

    Refuses unless the requester has been verified. The check lives here,
    not in the route, so any future caller — another endpoint, a
    background job, a bulk tool — hits the same wall rather than
    reimplementing the guard and getting it wrong.
    """
    if dsar.verification_status != "verified":
        raise DsarVerificationRequired(
            "This request cannot be exported until the data subject's identity has been "
            "verified. Fulfilling an unverified access request risks disclosing personal "
            "data to the wrong person."
        )

    payload = build_export_payload(dsar).encode("utf-8")
    filename = f"dsar-{dsar.id}.txt"
    dsar.export_generated_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.export_generated",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={"bytes": len(payload), "verification_status": dsar.verification_status},
    )
    return payload, filename
