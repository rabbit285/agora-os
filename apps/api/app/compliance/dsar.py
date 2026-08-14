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

Discovery is deliberately narrow. It searches sources this organization
owns, scoped to the organization, matching on the requester's email. It
does not attempt to be exhaustive, and the export says so: a DSAR
response is signed by a human who is accountable for its completeness,
and a tool that implies it found everything invites that human to stop
looking.
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
) -> DSAR:
    """Record the outcome of identity verification.

    Both outcomes are recorded. A failed verification is a fact about the
    request that the audit trail needs — "we refused this one, and why" is
    as important to be able to show as a completed response.
    """
    dsar.verification_status = "verified" if verified else "failed"
    dsar.verification_method = method
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
        after_state={"verification_status": dsar.verification_status, "method": method},
    )
    return dsar


async def run_data_discovery(
    db: AsyncSession, *, organization_id: uuid.UUID, dsar: DSAR, actor_user_id: uuid.UUID | None
) -> dict[str, Any]:
    """Search this organization's own records for the requester.

    Imports are local because these are other modules' tables and a
    top-level import would couple the compliance package to all of them
    at load time. Counts and identifiers are returned rather than full
    records: this is a map of where the person appears, which is what a
    case worker needs to decide what to include, and it keeps the
    discovery result itself from becoming a second copy of the data.
    """
    from app.identity.models import User
    from app.sales.models import Contact, Lead
    from app.support.models import Customer, Ticket

    email = dsar.requester_email.strip().lower()
    sources: list[dict[str, Any]] = []

    # Organization members.
    user_rows = list(
        (
            await db.execute(select(User.id, User.email).where(func.lower(User.email) == email))
        ).all()
    )
    sources.append(
        {
            "source": "Identity — user accounts",
            "matches": len(user_rows),
            "record_ids": [str(r[0]) for r in user_rows],
        }
    )

    # Support customers and their tickets.
    customer_rows = list(
        (
            await db.execute(
                select(Customer.id).where(
                    Customer.organization_id == organization_id,
                    func.lower(Customer.email) == email,
                )
            )
        )
        .scalars()
        .all()
    )
    ticket_count = 0
    if customer_rows:
        ticket_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Ticket)
                    .where(
                        Ticket.organization_id == organization_id,
                        Ticket.customer_id.in_(customer_rows),
                    )
                )
            ).scalar_one()
        )
    sources.append(
        {
            "source": "Support — customers",
            "matches": len(customer_rows),
            "record_ids": [str(c) for c in customer_rows],
        }
    )
    sources.append({"source": "Support — tickets", "matches": ticket_count, "record_ids": []})

    # Sales contacts and leads.
    contact_rows = list(
        (
            await db.execute(
                select(Contact.id).where(
                    Contact.organization_id == organization_id,
                    func.lower(Contact.email) == email,
                )
            )
        )
        .scalars()
        .all()
    )
    sources.append(
        {
            "source": "Sales — contacts",
            "matches": len(contact_rows),
            "record_ids": [str(c) for c in contact_rows],
        }
    )

    # A Lead carries no email of its own — it points at a Contact. Reached
    # through the contacts matched above rather than by a column that does
    # not exist, which is also the correct relationship: a lead is about a
    # person, it is not itself a person.
    lead_rows: list[uuid.UUID] = []
    if contact_rows:
        lead_rows = list(
            (
                await db.execute(
                    select(Lead.id).where(
                        Lead.organization_id == organization_id,
                        Lead.contact_id.in_(contact_rows),
                    )
                )
            )
            .scalars()
            .all()
        )
    sources.append(
        {
            "source": "Sales — leads",
            "matches": len(lead_rows),
            "record_ids": [str(lead) for lead in lead_rows],
        }
    )

    findings = {
        "email": email,
        "sources": sources,
        "total_matches": sum(int(s["matches"]) for s in sources),
        # Stated in the result itself, not only in documentation, because
        # this string travels with the export.
        "coverage_note": (
            "Searched the sources listed above only. Systems outside Veyntra, and unstructured "
            "content such as free-text notes or attachments, were not searched. A case worker "
            "remains responsible for the completeness of the response."
        ),
    }

    dsar.discovery_findings = findings
    dsar.discovery_run_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.discovery_run",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={"total_matches": findings["total_matches"], "sources": len(sources)},
    )
    return findings


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
