"""Who conducted the audit, and whose organization it was.

Two identities a formal report has to get right, and got wrong in two
different ways.

**"Zach Warren (external)".** The auditor type was inferred from
`auditor_user_id IS NULL`. That column only started being written when
the create form gained a picker, so every audit created before it stored
its auditor as text — and the inference labelled all of them external,
including the internal ones. Internal-versus-external is a fact about
organization membership. It is now recorded, reconciled from membership
for legacy rows, and left unresolved rather than guessed.

**"Organization: xwarren@outlook.com".** Not a derivation bug: the
organization record genuinely holds that string in its name field,
entered at signup. The report was faithfully printing a corrupt record.
It now refuses to name a person's mailbox as a company and says the name
is not configured, which is the truth and points at the fix.

The third identity, kept separate from both: whoever pressed generate.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import audit_identity, audit_report, audit_state
from app.compliance.audit_render import render_audit_report_pdf
from app.compliance.models import Audit, AuditItem, Framework, Requirement
from app.core.models import Membership, Organization
from app.identity.models import User


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _member(
    db: AsyncSession, organization_id: uuid.UUID, *, name: str, email: str
) -> User:
    user = User(email=email, full_name=name, hashed_password="x")
    db.add(user)
    await db.flush()
    db.add(Membership(organization_id=organization_id, user_id=user.id))
    await db.flush()
    return user


async def _scope(db: AsyncSession, audit: Audit, *, decision: str = "observation") -> None:
    """One reviewed requirement, so the audit is reportable.

    A report of an audit that scoped nothing is refused, which is correct
    and not what these tests are about.
    """
    framework = (
        await db.execute(select(Framework).where(Framework.key == "iso42001"))
    ).scalars().first()
    if framework is None:
        framework = Framework(key="iso42001", name="ISO 42001", description=None)
        db.add(framework)
        await db.flush()
    requirement = (
        await db.execute(
            select(Requirement).where(Requirement.framework_id == framework.id)
        )
    ).scalars().first()
    if requirement is None:
        requirement = Requirement(
            framework_id=framework.id,
            reference_code="4.1",
            title="Understanding the organization and its context",
            description=None,
        )
        db.add(requirement)
        await db.flush()
    audit.framework_id = framework.id
    audit.framework_name = framework.name
    db.add(
        AuditItem(
            organization_id=audit.organization_id,
            audit_id=audit.id,
            requirement_id=requirement.id,
            reference_code=requirement.reference_code,
            requirement_title=requirement.title,
            framework_key="iso42001",
            control_title="Maintain an inventory of AI systems",
            prepared_status="evidenced",
            decision=decision,
            evidence_snapshot=[],
        )
    )
    await db.flush()


def _pdf_text(payload: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# --- the organization name ---------------------------------------------


def test_an_email_is_never_the_name_of_an_organization() -> None:
    """§1/§12: the reported value, refused at the resolver.

    The record is real and the value is not a company name. A report that
    prints somebody's mailbox as the audited organization is worse than
    one that admits the name is missing.
    """
    assert (
        audit_identity.organization_display_name(
            Organization(name="Agora Origin", slug="agora-origin")
        )
        == "Agora Origin"
    )
    for bad in ("xwarren@outlook.com", "  zach@example.co.uk  ", ""):
        assert (
            audit_identity.organization_display_name(
                Organization(name=bad, slug="x")
            )
            is None
        )
    assert audit_identity.organization_display_name(None) is None
    # A name that merely contains an @ is still a name.
    assert (
        audit_identity.organization_display_name(
            Organization(name="Smith @ Partners", slug="x")
        )
        == "Smith @ Partners"
    )


@pytest.mark.asyncio
async def test_the_report_names_the_organization_from_its_own_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§1: audit.organization_id → Organization → name. Nothing else."""
    org_id = await _signup(client, "identity1@example.com", "Agora Origin")
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_name="Zach Warren",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.organization_name == "Agora Origin"
    assert preview.organization_name_configured is True
    # And nothing about the person who signed up reached the report.
    assert "identity1@example.com" not in _pdf_text(
        render_audit_report_pdf(preview)
    )


@pytest.mark.asyncio
async def test_an_organization_named_after_an_email_reports_it_as_unconfigured(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: no fallback to an email address, ever."""
    org_id = await _signup(client, "identity2@example.com", "Placeholder")
    organization = await db_session.get(Organization, org_id)
    organization.name = "xwarren@outlook.com"
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_name="Zach Warren",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.organization_name == audit_identity.UNCONFIGURED_ORGANIZATION
    assert preview.organization_name_configured is False

    text = _pdf_text(render_audit_report_pdf(preview))
    assert "xwarren@outlook.com" not in text
    assert "Organization name not configured" in text
    # And the document says how to fix it.
    assert "Organization Settings" in text.replace("\n", " ")


# --- internal versus external ------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_account_id_no_longer_means_external(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3: the inference that produced "Zach Warren (external)".

    An audit carrying only a name has not told us anything about whether
    that person was external. Unresolved is the honest answer.
    """
    org_id = await _signup(client, "identity3@example.com", "Agora Origin")
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_name="Somebody Unmatched",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    identity = await audit_identity.resolve_auditor(db_session, audit=audit)
    assert identity.name == "Somebody Unmatched"
    assert identity.auditor_type is None
    assert identity.unresolved is True

    text = _pdf_text(
        render_audit_report_pdf(
            await audit_report.build_preview(db_session, audit=audit)
        )
    ).replace("\n", " ")
    assert "(external)" not in text
    assert "Somebody Unmatched" in text
    assert "Not recorded for this audit" in text


@pytest.mark.asyncio
async def test_an_internal_auditor_is_named_without_a_suffix(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2/§5/§16: the reported case, end to end."""
    org_id = await _signup(client, "identity4@example.com", "Agora Origin")
    zach = (
        await db_session.execute(
            select(User).where(User.email == "identity4@example.com")
        )
    ).scalars().first()

    people = await client.get("/api/v1/organizations/current/people")
    assert any(person["id"] == str(zach.id) for person in people.json())

    created = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "ISO 42001 Internal Audit",
            "auditor_user_id": str(zach.id),
            "auditor_name": "Zach Warren",
            "auditor_type": "internal",
            "scope": "AI governance controls and the evidence behind them.",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["auditor_user_id"] == str(zach.id)
    assert body["auditor_type"] == "internal"
    assert body["auditor_name"] == "Zach Warren"

    audit = await db_session.get(Audit, uuid.UUID(body["id"]))
    audit.organization_id == org_id
    audit_state.apply_status(audit, "completed")
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.auditor.name == "Zach Warren"
    assert preview.auditor.auditor_type == "internal"
    assert preview.auditor.type_label == "Internal"
    assert preview.auditor.organization is None
    assert preview.sign_off.auditor.type_label == "Internal"

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Zach Warren (external)" not in text
    assert "(external)" not in text
    assert "Auditor type" in text
    assert "Internal" in text
    assert "Organization Agora Origin" in text


@pytest.mark.asyncio
async def test_an_external_auditor_carries_their_firm_as_its_own_field(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6/§18: External is useful here, and structured."""
    await _signup(client, "identity5@example.com", "Agora Origin")
    created = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "ISO 42001 External Audit",
            "auditor_name": "Jane Smith",
            "auditor_type": "external",
            "auditor_organization": "ABC Compliance Ltd.",
            "scope": "AI governance controls and the evidence behind them.",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["auditor_user_id"] is None
    assert body["auditor_type"] == "external"

    audit = await db_session.get(Audit, uuid.UUID(body["id"]))
    audit_state.apply_status(audit, "completed")
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.auditor.name == "Jane Smith"
    assert preview.auditor.type_label == "External"
    assert preview.auditor.organization == "ABC Compliance Ltd."

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Jane Smith" in text
    # §6: not glued onto the person's name.
    assert "Jane Smith (external)" not in text
    assert "Auditor organization" in text
    assert "ABC Compliance Ltd." in text


@pytest.mark.asyncio
async def test_an_auditor_who_is_not_a_member_cannot_be_recorded_as_internal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Internal means a member of this organization, checked at the door."""
    await _signup(client, "identity6@example.com", "Agora Origin")
    other_org = await _signup(client, "identity7@example.com", "Another Company")
    outsider = (
        await db_session.execute(
            select(User).where(User.email == "identity7@example.com")
        )
    ).scalars().first()
    assert outsider is not None

    # Back to the first organization.
    await client.post(
        "/api/v1/auth/login",
        json={"email": "identity6@example.com", "password": "correct-horse-battery"},
    )
    refused = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "ISO 42001 Internal Audit",
            "auditor_user_id": str(outsider.id),
            "auditor_type": "internal",
            "scope": "AI governance controls and the evidence behind them.",
        },
    )
    assert refused.status_code == 422
    assert "not a member of this organization" in refused.text
    assert other_org is not None


# --- reconciling the audits that already exist --------------------------


@pytest.mark.asyncio
async def test_reconciliation_links_an_unambiguous_name_to_its_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: the repair for audits created before the picker existed."""
    org_id = await _signup(client, "identity8@example.com", "Agora Origin")
    zach = (
        await db_session.execute(
            select(User).where(User.email == "identity8@example.com")
        )
    ).scalars().first()

    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 - Agora Origin",
        auditor_name="Zach Warren",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()
    assert audit.auditor_user_id is None
    assert audit.auditor_type is None

    result = await audit_identity.reconcile_auditors(
        db_session, organization_id=org_id
    )
    await db_session.commit()

    assert result.linked == 1
    assert result.ambiguous == []
    assert result.unmatched == []
    await db_session.refresh(audit)
    assert audit.auditor_user_id == zach.id
    assert audit.auditor_type == "internal"

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.auditor.type_label == "Internal"


@pytest.mark.asyncio
async def test_reconciliation_refuses_to_choose_between_two_people(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: "If ambiguous: do not guess."

    Attributing an audit to the wrong person is worse than leaving it
    unresolved, and a duplicate name is evidence of nothing.
    """
    org_id = await _signup(client, "identity9@example.com", "Agora Origin")
    await _member(
        db_session, org_id, name="Zach Warren", email="zach.warren.2@example.com"
    )
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 - Agora Origin",
        auditor_name="Zach Warren",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    result = await audit_identity.reconcile_auditors(
        db_session, organization_id=org_id
    )
    assert result.linked == 0
    assert result.ambiguous == ["Zach Warren"]

    await db_session.refresh(audit)
    assert audit.auditor_user_id is None
    # And crucially it was not resolved the other way either.
    assert audit.auditor_type is None

    identity = await audit_identity.resolve_auditor(db_session, audit=audit)
    assert identity.unresolved is True
    assert identity.auditor_type is None


@pytest.mark.asyncio
async def test_reconciliation_leaves_an_unmatched_name_alone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A name matching nobody is not therefore an external firm."""
    org_id = await _signup(client, "identity10@example.com", "Agora Origin")
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_name="Nordic Assurance Partners",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    result = await audit_identity.reconcile_auditors(
        db_session, organization_id=org_id
    )
    assert result.linked == 0
    assert result.unmatched == ["Nordic Assurance Partners"]
    await db_session.refresh(audit)
    assert audit.auditor_type is None


@pytest.mark.asyncio
async def test_reconciliation_is_reachable_and_reports_what_it_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "identity11@example.com", "Agora Origin")
    for title, name in (
        ("Audit One", "Zach Warren"),
        ("Audit Two", "Nordic Assurance Partners"),
    ):
        audit = Audit(
            organization_id=org_id,
            title=title,
            auditor_name=name,
            scope="AI governance controls and the evidence behind them.",
        )
        audit_state.apply_status(audit, "completed")
        db_session.add(audit)
    await db_session.commit()

    response = await client.post("/api/v1/compliance/audits/reconcile-auditors")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["linked"] == 1
    assert body["unmatched"] == ["Nordic Assurance Partners"]
    assert body["ambiguous"] == []


# --- the third identity -------------------------------------------------


@pytest.mark.asyncio
async def test_the_report_generator_never_replaces_the_auditor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§7/§17: two roles, two fields, even when they are two people."""
    org_id = await _signup(client, "identity12@example.com", "Agora Origin")
    auditor = await _member(
        db_session, org_id, name="Sarah Lee", email="sarah.lee@example.com"
    )
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_user_id=auditor.id,
        auditor_name="Sarah Lee",
        auditor_type="internal",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.flush()
    await _scope(db_session, audit)
    await db_session.commit()

    # Zach — a different member — issues the report.
    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    assert preview["auditor"]["name"] == "Sarah Lee"

    generated = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": preview["digest"]},
    )
    assert generated.status_code == 201, generated.text
    assert generated.json()["generated_by_name"] == "Zach Warren"

    from app.compliance.models import AuditReport

    stored = await db_session.get(AuditReport, uuid.UUID(generated.json()["id"]))
    sign_off = stored.contents["sign_off"]
    assert sign_off["auditor_name"] == "Sarah Lee"
    assert sign_off["auditor_type"] == "internal"
    assert sign_off["generated_by"] == "Zach Warren"


@pytest.mark.asyncio
async def test_a_renamed_auditor_still_reads_correctly_on_an_old_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A linked account is resolved to its current display name, while
    the identity itself stays exactly as recorded."""
    org_id = await _signup(client, "identity13@example.com", "Agora Origin")
    person = await _member(
        db_session, org_id, name="Zachary Warren", email="zw@example.com"
    )
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_user_id=person.id,
        auditor_name="Zach Warren",
        auditor_type="internal",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    identity = await audit_identity.resolve_auditor(db_session, audit=audit)
    assert identity.name == "Zachary Warren"
    assert identity.auditor_type == "internal"


@pytest.mark.asyncio
async def test_a_linked_account_is_internal_whatever_an_old_row_says(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Membership decides, not a stale column value."""
    org_id = await _signup(client, "identity14@example.com", "Agora Origin")
    person = (
        await db_session.execute(
            select(User).where(User.email == "identity14@example.com")
        )
    ).scalars().first()
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        auditor_user_id=person.id,
        auditor_name="Zach Warren",
        # Contradictory, and the account wins.
        auditor_type="external",
        auditor_organization="Nordic Assurance Partners",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db_session.add(audit)
    await db_session.commit()

    identity = await audit_identity.resolve_auditor(db_session, audit=audit)
    assert identity.auditor_type == "internal"
    assert identity.organization is None
