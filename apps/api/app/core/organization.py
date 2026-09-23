"""What the organization is called, resolved in one place.

Every surface that names the organization — an audit report, a security
review summary, a public Trust Center page — has to answer the same
question, and answering it separately in each renderer is how one of
them ends up publishing something the others would refuse to print.

So there is one resolver, and it holds one rule: **an organization is
named by its own record, and never by a person.** Not a user's email,
not an email domain, not whoever generated the document. If the record
cannot supply a usable name, the surface says so rather than
substituting an identity that belongs to a human being.

The second rule is why this module exists at all: a name that *is* an
email address is not a usable organization name, whatever the column
says. That value gets into the record the only way it can — somebody
submits it at signup — and once there it propagates silently into
reports and, worse, onto a public page. Catching it at the boundary
stops it arriving; catching it here stops the copies already stored
from being published.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Organization

# What a surface prints when the record cannot supply a name. Never a
# fallback to anything derived from a person: a document naming a human's
# mailbox as the audited organization is worse than one admitting a gap.
UNCONFIGURED = "Organization name not configured"

# Rough by design, and only ever used to reject. An organization may call
# itself almost anything; what it must not be called in a report — or on
# a public page — is somebody's email address.
#
# A name that merely contains an "@" ("Smith @ Partners") is a name. This
# matches the whole string being an address and nothing else.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def looks_like_an_email(value: str | None) -> bool:
    return bool(_EMAIL.match((value or "").strip()))


def display_name(organization: Organization | None) -> str | None:
    """The organization's name, or nothing.

    Returns None rather than a substitute, so every caller has to decide
    what to show — and none of them can fall through to an email address
    by accident.
    """
    if organization is None:
        return None
    name = (organization.name or "").strip()
    if not name or looks_like_an_email(name):
        return None
    return name


@dataclass
class OrganizationIdentity:
    """How an organization should be named on a given surface."""

    id: uuid.UUID | None
    # The name to print, already decided. Never None: callers get either
    # the real name or the honest placeholder, so no renderer has to
    # invent a fallback of its own.
    name: str
    configured: bool
    # What the record actually holds, when that is the problem. Shown so
    # a person can recognise the wrong value instead of being told
    # something is missing when a field is plainly filled in.
    recorded_name: str | None = None
    problem: str | None = None


async def resolve(
    db: AsyncSession, organization_id: uuid.UUID | None
) -> OrganizationIdentity:
    """Name the organization behind a record.

    The only supported path: an `organization_id` on the thing being
    rendered, to the `Organization` row, to its name.
    """
    organization = (
        await db.get(Organization, organization_id) if organization_id else None
    )
    return identify(organization)


def identify(organization: Organization | None) -> OrganizationIdentity:
    """The same decision, for a row already loaded."""
    if organization is None:
        return OrganizationIdentity(
            id=None, name=UNCONFIGURED, configured=False, problem="missing"
        )

    recorded = (organization.name or "").strip() or None
    name = display_name(organization)
    if name is not None:
        return OrganizationIdentity(
            id=organization.id, name=name, configured=True, recorded_name=recorded
        )

    # "Not configured" is misleading when the field is plainly filled in
    # with the wrong thing, so the two cases are distinguished and the
    # recorded value travels with the answer.
    problem = "email_address" if recorded else "empty"
    return OrganizationIdentity(
        id=organization.id,
        name=UNCONFIGURED,
        configured=False,
        recorded_name=recorded,
        problem=problem,
    )


def name_problem(value: str | None) -> str | None:
    """Why this cannot be an organization name, if it cannot.

    Used at the write boundary — signup and settings — so a bad value is
    refused where a person can still fix it, rather than discovered
    later in a report.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return "An organization name is required."
    if looks_like_an_email(cleaned):
        return (
            "That looks like an email address rather than an organization name. "
            "Enter the name of your company or team — it appears on your audit "
            "reports and on anything you share with customers."
        )
    return None


async def misconfigured(db: AsyncSession) -> list[Organization]:
    """Organizations whose name cannot be printed.

    Reported rather than repaired. The name a customer meant to enter is
    not recoverable from anywhere — signup keeps no separate copy, and
    the legal entity created alongside it carries the same submitted
    value — so guessing would put an invented name on their audit
    reports. Somebody has to be asked.
    """
    rows = (await db.execute(select(Organization))).scalars().all()
    return [org for org in rows if display_name(org) is None]


__all__ = [
    "UNCONFIGURED",
    "OrganizationIdentity",
    "display_name",
    "identify",
    "looks_like_an_email",
    "misconfigured",
    "name_problem",
    "resolve",
]
