"""What the organization is called, and where that comes from.

The reported symptom was an audit report saying "Organization name not
configured" for an account whose owner had entered a name at signup.

The trail says otherwise, and these pin what it says. Signup writes
`payload.organization_name` straight onto the record and creates a legal
entity from the same field; both held the same email address, the row
had never been updated after the insert, and no rename event existed.
Nothing lost the name — the value submitted was an email address.

So the fix is a boundary rather than a repair: an email address is
refused as an organization name at both write paths, where a person can
still correct it, instead of surfacing three weeks later inside a PDF.
And one resolver answers "what is this organization called" for every
surface that asks, because a second copy of that rule is how the public
Trust Center page ends up publishing what the reports refuse to print.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import organization as org_identity
from app.core.models import LegalEntity, Membership, Organization


# --- the rule -----------------------------------------------------------


def test_an_email_address_is_not_an_organization_name() -> None:
    assert org_identity.looks_like_an_email("xwarren@outlook.com") is True
    assert org_identity.looks_like_an_email("  zach@example.co.uk  ") is True
    assert org_identity.looks_like_an_email("Agora Origin") is False
    # A name that merely contains an "@" is a name.
    assert org_identity.looks_like_an_email("Smith @ Partners") is False
    assert org_identity.looks_like_an_email("") is False
    assert org_identity.looks_like_an_email(None) is False


def test_the_resolver_distinguishes_missing_from_wrong() -> None:
    """"Not configured" is misleading when the field is plainly filled in.

    A person who reads that, opens settings and sees a value there has
    been told something untrue about their own data.
    """
    real = org_identity.identify(Organization(name="Agora Origin", slug="agora"))
    assert real.name == "Agora Origin"
    assert real.configured is True
    assert real.problem is None

    wrong = org_identity.identify(
        Organization(name="xwarren@outlook.com", slug="x")
    )
    assert wrong.name == org_identity.UNCONFIGURED
    assert wrong.configured is False
    assert wrong.problem == "email_address"
    # The value travels with the answer, so a person can recognise it.
    assert wrong.recorded_name == "xwarren@outlook.com"

    empty = org_identity.identify(Organization(name="   ", slug="x"))
    assert empty.problem == "empty"
    assert empty.recorded_name is None

    assert org_identity.identify(None).problem == "missing"


def test_the_write_boundary_explains_itself() -> None:
    assert org_identity.name_problem("Agora Origin") is None
    assert "required" in org_identity.name_problem("")
    problem = org_identity.name_problem("xwarren@outlook.com")
    assert "looks like an email address" in problem
    # And says why it matters, rather than just refusing.
    assert "audit reports" in problem


# --- signup -------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_persists_the_organization_name_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: entered once, and every surface reads the same record."""
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "acme@example.com",
            "password": "correct-horse-battery",
            "full_name": "Test User",
            "organization_name": "Acme Corp",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization"]["name"] == "Acme Corp"
    org_id = uuid.UUID(body["organization"]["id"])

    # The authoritative record.
    organization = await db_session.get(Organization, org_id)
    assert organization.name == "Acme Corp"

    # §5: settings shows it without a second setup step.
    settings = await client.get("/api/v1/organizations/current")
    assert settings.json()["name"] == "Acme Corp"

    # §2: and the account reaches it through membership.
    membership = (
        await db_session.execute(
            select(Membership).where(Membership.organization_id == org_id)
        )
    ).scalars().first()
    assert membership is not None

    # §3: the legal entity created alongside carries the same value —
    # which is exactly why both were wrong together on the reported
    # account.
    entity = (
        await db_session.execute(
            select(LegalEntity).where(LegalEntity.organization_id == org_id)
        )
    ).scalars().first()
    assert entity.name == "Acme Corp"


@pytest.mark.asyncio
async def test_signup_refuses_an_email_as_the_organization_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The root cause, stopped where a person can still fix it.

    This value reaches the column the only way it can — submitted here —
    and once stored it propagates into every report and onto the public
    Trust Center page.
    """
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "someone@example.com",
            "password": "correct-horse-battery",
            "full_name": "Some One",
            "organization_name": "someone@example.com",
        },
    )
    assert response.status_code == 422
    assert "looks like an email address" in response.text

    # And nothing was created.
    orgs = (await db_session.execute(select(Organization))).scalars().all()
    assert not any(org.name == "someone@example.com" for org in orgs)


@pytest.mark.asyncio
async def test_settings_refuses_it_too(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A boundary that guards one of two write paths is not a boundary."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "settings@example.com",
            "password": "correct-horse-battery",
            "full_name": "Test User",
            "organization_name": "Acme Corp",
        },
    )

    refused = await client.patch(
        "/api/v1/organizations/current", json={"name": "settings@example.com"}
    )
    assert refused.status_code == 422
    assert "looks like an email address" in refused.text

    # §5: a real rename still works, and reaches the same record.
    renamed = await client.patch(
        "/api/v1/organizations/current", json={"name": "Acme Corporation"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Acme Corporation"


# --- the surfaces -------------------------------------------------------


@pytest.mark.asyncio
async def test_every_surface_reads_the_same_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: one resolver, so the surfaces cannot disagree."""
    from app.compliance import audit_identity, audit_state, audit_report
    from app.compliance.models import Audit, AuditItem, Framework, Requirement

    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "surfaces@example.com",
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    org_id = uuid.UUID(signup.json()["organization"]["id"])

    framework = Framework(key="iso42001x", name="ISO 42001", description=None)
    db_session.add(framework)
    await db_session.flush()
    requirement = Requirement(
        framework_id=framework.id,
        reference_code="9.2",
        title="Internal audit",
        description=None,
    )
    db_session.add(requirement)
    await db_session.flush()

    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        framework_id=framework.id,
        framework_name="ISO 42001",
        auditor_name="Zach Warren",
        auditor_type="internal",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.flush()
    db_session.add(
        AuditItem(
            organization_id=org_id,
            audit_id=audit.id,
            requirement_id=requirement.id,
            reference_code="9.2",
            requirement_title="Internal audit",
            framework_key="iso42001x",
            prepared_status="evidenced",
            decision="observation",
            evidence_snapshot=[],
        )
    )
    await db_session.commit()

    # Settings.
    assert (await client.get("/api/v1/organizations/current")).json()[
        "name"
    ] == "Agora Origin"

    # §6: the audit report preview and the PDF.
    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.organization_name == "Agora Origin"
    assert preview.organization_name_configured is True

    # §7: the auditor is a separate identity and stays one.
    assert preview.auditor.name == "Zach Warren"
    assert preview.auditor.type_label == "Internal"

    # The compatibility shim still answers the same way.
    organization = await db_session.get(Organization, org_id)
    assert (
        audit_identity.organization_display_name(organization) == "Agora Origin"
    )


@pytest.mark.asyncio
async def test_the_public_page_never_publishes_an_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The one surface where getting this wrong publishes to the internet.

    The Trust Center read `organization.name` straight off the column, so
    an account in the reported state would have served a person's email
    address as the name of the company.
    """
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "trust@example.com",
            "password": "correct-horse-battery",
            "full_name": "Test User",
            "organization_name": "Agora Origin",
        },
    )
    org_id = uuid.UUID(signup.json()["organization"]["id"])
    organization = await db_session.get(Organization, org_id)

    # Forced into the bad state the way the reported account got there,
    # bypassing the boundary that now prevents it.
    organization.name = "trust@example.com"
    await db_session.commit()

    public = await client.get(f"/api/v1/trust-center/public/{organization.slug}")
    assert public.status_code == 200, public.text
    assert public.json()["organization_name"] == org_identity.UNCONFIGURED
    assert "trust@example.com" not in public.text


# --- finding the accounts that need a person ----------------------------


@pytest.mark.asyncio
async def test_misconfigured_organizations_are_reported_not_guessed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: the name is not recoverable, so it is not invented.

    Signup keeps no separate copy of what was submitted, and the legal
    entity created alongside carries the same value — which on the
    reported account was the same email address. There is nothing to
    back-fill *from*, so the repair surfaces the accounts and stops.
    """
    good = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "fine@example.com",
            "password": "correct-horse-battery",
            "full_name": "Test User",
            "organization_name": "Perfectly Fine Ltd",
        },
    )
    bad = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "broken@example.com",
            "password": "correct-horse-battery",
            "full_name": "Test User",
            "organization_name": "Placeholder",
        },
    )
    broken_id = uuid.UUID(bad.json()["organization"]["id"])
    broken = await db_session.get(Organization, broken_id)
    broken.name = "broken@example.com"
    await db_session.commit()

    flagged = await org_identity.misconfigured(db_session)
    names = {org.name for org in flagged}
    assert "broken@example.com" in names
    assert "Perfectly Fine Ltd" not in names
    assert good.status_code == 200

    # A real name is never overwritten by anything here — the function
    # only reports.
    await db_session.refresh(broken)
    assert broken.name == "broken@example.com"
