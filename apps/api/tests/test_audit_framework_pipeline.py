"""Every framework, through the same audit pipeline.

The reported failure: selecting any framework made Create or Prepare
Audit fail, while an audit with no framework could be created. Not
GDPR-specific — a shared break in the framework/audit integration.

The cause was in evidence resolution, and the reason no existing test
caught it is worth writing down: the audit workspace read three fields
straight off the `Evidence` row that are not columns there. An
organization with no evidence never reaches the line, and every test
fixture in this suite had no evidence. The first organization with a
document attached to a control hit it on their first audit.

So these run the pipeline **with evidence attached**, across every
framework in the catalog, and assert the states an audit must never be
allowed to reach.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import audit_state, audit_workspace
from app.compliance.audit_reconcile import reconcile_audits
from app.compliance.audit_scope_text import SUGGESTED_SCOPE, suggested_scope
from app.compliance.models import (
    Audit,
    AuditFinding,
    AuditItem,
    Control,
    ControlMapping,
    Evidence,
    Framework,
    Requirement,
)
from app.core.models import File, Task


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    """The organization id. Use `_signup_full` when a user id is needed."""
    _user_id, org_id = await _signup_full(client, email, org)
    return org_id


async def _signup_full(
    client: AsyncClient, email: str, org: str
) -> tuple[uuid.UUID, uuid.UUID]:
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
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


# Every framework the catalog ships, with enough requirements to scope.
_FRAMEWORKS = {
    "gdpr": ("GDPR", ["Art. 5", "Art. 30", "Art. 32", "Art. 35"]),
    "eu_ai_act": ("EU AI Act", ["Art. 9", "Art. 14", "Art. 72"]),
    "iso42001": ("ISO 42001", ["4.1", "6.1", "9.2"]),
    "iso27001": ("ISO 27001", ["A.5.1", "A.8.1"]),
    "soc2": ("SOC 2", ["CC1.1", "CC6.1"]),
    "nis2": ("NIS2", ["Art. 21", "Art. 23"]),
    "dora": ("DORA", ["Art. 5", "Art. 11"]),
}


async def _framework(db: AsyncSession, key: str) -> Framework:
    name, codes = _FRAMEWORKS[key]
    framework = (
        await db.execute(select(Framework).where(Framework.key == key))
    ).scalars().first()
    if framework is None:
        framework = Framework(key=key, name=name, description=None)
        db.add(framework)
        await db.flush()
    existing = {
        code
        for code in (
            await db.execute(
                select(Requirement.reference_code).where(
                    Requirement.framework_id == framework.id
                )
            )
        ).scalars()
    }
    for code in codes:
        if code not in existing:
            db.add(
                Requirement(
                    framework_id=framework.id,
                    reference_code=code,
                    title=f"{name} {code}",
                    description=None,
                )
            )
    await db.flush()
    return framework


async def _control_with_evidence(
    db: AsyncSession,
    org_id: uuid.UUID,
    requirement: Requirement,
    uploaded_by: uuid.UUID,
) -> Control:
    """A control answering a requirement, with a document behind it.

    The evidence is the point. Without it the branch that failed in
    production is never executed, which is exactly how this shipped.
    """
    control = Control(
        organization_id=org_id,
        title=f"Control for {requirement.reference_code}",
        status="implemented",
    )
    db.add(control)
    await db.flush()
    db.add(ControlMapping(control_id=control.id, requirement_id=requirement.id))

    file_record = File(
        organization_id=org_id,
        storage_key=f"test/{uuid.uuid4()}",
        original_filename="Information Security Policy.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        uploaded_by=uploaded_by,
    )
    db.add(file_record)
    await db.flush()
    db.add(
        Evidence(
            organization_id=org_id,
            control_id=control.id,
            file_id=file_record.id,
            title="Information Security Policy",
        )
    )
    await db.flush()
    return control


# --- Part A: every framework, with evidence on file --------------------


@pytest.mark.anyio
@pytest.mark.parametrize("key", sorted(_FRAMEWORKS))
async def test_every_framework_prepares_with_evidence_attached(
    client: AsyncClient, db_session: AsyncSession, key: str
) -> None:
    """The reported bug, per framework.

    It was never framework-specific: the failure was in resolving the
    evidence a control carries, which happens identically whichever
    standard is being audited.
    """
    user_id, org_id = await _signup_full(
        client, f"fw-{key}-{uuid.uuid4().hex[:6]}@example.com", f"FW {key} Org"
    )
    framework = await _framework(db_session, key)
    requirements = list(
        (
            await db_session.execute(
                select(Requirement).where(Requirement.framework_id == framework.id)
            )
        )
        .scalars()
        .all()
    )
    # Evidence on the first requirement's control — the branch that broke.
    await _control_with_evidence(db_session, org_id, requirements[0], user_id)
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": f"{framework.name} Internal Audit",
            "framework_id": str(framework.id),
            "auditor_name": "Zach Warren",
            "scope": suggested_scope(key) or "Full scope",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["progress"]["scoped"] == len(requirements), key
    assert body["prepared_at"] is not None, key

    # And the evidence actually travelled onto the row it belongs to.
    items = (
        await client.get(f"/api/v1/compliance/audits/{body['id']}/items")
    ).json()
    with_evidence = [item for item in items if item["evidence_snapshot"]]
    assert with_evidence, f"{key}: no row carried its evidence"
    entry = with_evidence[0]["evidence_snapshot"][0]
    assert entry["title"] == "Information Security Policy"
    # §17: what the auditor needs, and nothing internal.
    assert "chunk" not in str(entry).lower()


@pytest.mark.anyio
async def test_an_audit_scoped_against_one_framework_uses_only_its_requirements(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§43: ISO 42001 requirements, not GDPR's, not the AI Act's."""
    org_id = await _signup(client, f"iso-{uuid.uuid4().hex[:6]}@example.com", "Iso Org")
    iso = await _framework(db_session, "iso42001")
    await _framework(db_session, "gdpr")
    await _framework(db_session, "eu_ai_act")
    await db_session.commit()

    created = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "ISO 42001 Internal Audit",
            "framework_id": str(iso.id),
            "auditor_name": "Zach Warren",
            "scope": "AI governance, risk management and lifecycle controls.",
        },
    )
    assert created.status_code == 201, created.text

    items = (
        await client.get(f"/api/v1/compliance/audits/{created.json()['id']}/items")
    ).json()
    assert {item["framework_key"] for item in items} == {"iso42001"}
    assert {item["reference_code"] for item in items} == set(_FRAMEWORKS["iso42001"][1])


# --- Part C/F: an empty scope is a blocker, not a silent success -------


@pytest.mark.anyio
async def test_a_framework_nothing_applies_to_refuses_rather_than_scoping_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6/§44: distinguish "prepared and empty" from "prepared"."""
    org_id = await _signup(client, f"none-{uuid.uuid4().hex[:6]}@example.com", "None Org")
    # A framework with no requirements at all: nothing to scope against.
    framework = Framework(
        key=f"empty-{uuid.uuid4().hex[:6]}", name="Empty Standard", description=None
    )
    db_session.add(framework)
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "Empty Standard Audit",
            "framework_id": str(framework.id),
            "auditor_name": "Zach Warren",
            "scope": "Every requirement this standard defines, without exception.",
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    # §A2: a sentence somebody can act on, and a code the screen can use.
    assert "no requirements in the catalog" in error["message"]
    assert error["details"]["code"] == audit_workspace.NO_REQUIREMENTS_IN_CATALOG

    # Whether the half-made audit is rolled back is a property of the
    # request's transaction, and this suite shares one session between
    # the client and the test — so the pending row is visible here and
    # would not be in production. Asserted at the level this fixture can
    # actually observe: the request was refused, with a code.
    assert response.json()["error"]["details"]["code"]


@pytest.mark.anyio
async def test_an_audit_with_no_scope_cannot_be_started_or_completed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§13/§31: the state the reported audit was found in.

    Completed, against a framework, with nothing ever in scope. It got
    there because completion counted unreviewed rows and open findings,
    and an empty audit has neither — zero of zero looks exactly like a
    clean result.
    """
    org_id = await _signup(client, f"mt-{uuid.uuid4().hex[:6]}@example.com", "Empty Org")
    framework = await _framework(db_session, "iso42001")
    audit = Audit(
        organization_id=org_id,
        title="Scopeless audit",
        framework_id=framework.id,
        auditor_name="Zach Warren",
    )
    audit_state.apply_status(audit, "planned")
    db_session.add(audit)
    await db_session.commit()

    blockers = await audit_state.start_blockers(db_session, audit=audit)
    assert [blocker.code for blocker in blockers] == ["not_prepared", "empty_scope"]

    started = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "in_progress"}
    )
    assert started.status_code == 422
    assert "nothing to review" in started.json()["error"]["message"]

    # And it cannot be concluded either.
    completion = await audit_state.completion_blockers(db_session, audit=audit)
    assert [blocker.code for blocker in completion] == ["empty_scope"]


@pytest.mark.anyio
async def test_a_custom_audit_scopes_itself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: no framework is a choice, and it does not call preparation."""
    await _signup(client, f"cus-{uuid.uuid4().hex[:6]}@example.com", "Custom Org")

    created = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "Third-party datacentre walkthrough",
            "auditor_name": "Zach Warren",
            "scope": "Physical access controls at the Frankfurt facility.",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["prepared_at"] is None
    assert created.json()["progress"]["scoped"] == 0

    # A custom audit is not held to a framework's requirement count.
    started = await client.patch(
        f"/api/v1/compliance/audits/{created.json()['id']}/status",
        json={"status": "in_progress"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["started_at"] is not None


# --- Part Q: scope wording matches the framework -----------------------


def test_each_framework_has_its_own_scope_wording() -> None:
    """§38: a GDPR audit scoped as "AI governance" is mislabelled."""
    gdpr = suggested_scope("gdpr")
    iso = suggested_scope("iso42001")
    assert gdpr and iso and gdpr != iso
    assert "data subject rights" in gdpr
    assert "AI governance" not in gdpr
    assert "AI governance" in iso

    # Unrecognised frameworks get nothing rather than a plausible guess.
    assert suggested_scope("some-custom-standard") is None
    assert suggested_scope(None) is None
    assert suggested_scope("") is None


def test_every_catalog_framework_has_wording() -> None:
    assert set(SUGGESTED_SCOPE) == set(_FRAMEWORKS)


@pytest.mark.anyio
async def test_the_frameworks_list_carries_its_scope_wording(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, f"sc-{uuid.uuid4().hex[:6]}@example.com", "Scope Org")
    await _framework(db_session, "gdpr")
    await db_session.commit()

    listed = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(entry for entry in listed if entry["key"] == "gdpr")
    assert "data subject rights" in gdpr["suggested_audit_scope"]


# --- Part S: existing invalid audits -----------------------------------


@pytest.mark.anyio
async def test_reconciliation_repairs_what_it_can_and_flags_what_it_cannot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§40: correct the settleable, flag the ambiguous, invent nothing."""
    org_id = await _signup(client, f"rec-{uuid.uuid4().hex[:6]}@example.com", "Rec Org")
    framework = await _framework(db_session, "iso42001")

    # A contradiction with exactly one consistent reading.
    contradictory = Audit(
        organization_id=org_id,
        title="Planned but stamped complete",
        framework_id=framework.id,
        status="planned",
    )
    contradictory.completed_at = audit_state._now()
    db_session.add(contradictory)

    # A conclusion nobody can reconstruct.
    hollow = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        status="completed",
        framework_id=None,
        scope=None,
    )
    hollow.started_at = audit_state._now()
    hollow.completed_at = audit_state._now()
    db_session.add(hollow)
    await db_session.commit()

    dry = await reconcile_audits(db_session, organization_id=org_id, dry_run=True)
    assert dry.repaired == 0, "a dry run writes nothing"

    report = await reconcile_audits(
        db_session, organization_id=org_id, dry_run=False
    )
    await db_session.commit()

    by_code = {problem.code: problem for problem in report.problems}
    assert by_code["inconsistent_timestamps"].repaired is True
    assert by_code["completed_without_anything"].repaired is False

    await db_session.refresh(contradictory)
    assert contradictory.completed_at is None
    assert audit_state.check_invariants(contradictory) == []

    # The ambiguous one is untouched: its history is not ours to write.
    await db_session.refresh(hollow)
    assert hollow.status == "completed"
    assert hollow.completed_at is not None

    # §39: running it again changes nothing further.
    again = await reconcile_audits(
        db_session, organization_id=org_id, dry_run=False
    )
    assert again.repaired == 0
    assert again.flagged == 1


# ==================================================================
# Refinement: scope transparency, conclusions, completion by severity
# ==================================================================


def test_the_conclusion_is_not_the_severity() -> None:
    """§1: two vocabularies, deliberately not merged.

    "low" is how a finding is tracked; "Observation" is what the auditor
    concluded. A report that says "3 low findings" has thrown away the
    distinction the whole workflow rests on.
    """
    assert audit_state.CONCLUSION_LABELS["low"] == "Observation"
    assert audit_state.CONCLUSION_LABELS["high"] == "Major"
    # And the evidence vocabulary is a different set of words entirely.
    assert "Observation" not in set(
        __import__(
            "app.compliance.assessment", fromlist=["REQUIREMENT_STATUS_LABELS"]
        ).REQUIREMENT_STATUS_LABELS.values()
    )


def test_completion_rules_are_stated_by_severity() -> None:
    """§8: a policy question answered by a table, not by an `in` check."""
    rules = audit_state.SEVERITY_COMPLETION_RULE
    assert rules["low"] == "may_remain_open"
    assert rules["medium"] == "needs_owner"
    assert rules["high"] == "blocks"
    assert rules["critical"] == "blocks"
    assert audit_state.BLOCKING_SEVERITIES == ("high", "critical")
    assert audit_state.OWNED_SEVERITIES == ("medium",)


@pytest.mark.anyio
async def test_an_audit_completes_over_open_observations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§7/§23: the reported audit's exact shape.

    Three observations, all open, remediation continuing. Completing is
    valid and must not reopen when the work carries on afterwards.
    """
    user_id, org_id = await _signup_full(
        client, f"obs-{uuid.uuid4().hex[:6]}@example.com", "Obs Org"
    )
    framework = await _framework(db_session, "eu_ai_act")
    audit = Audit(
        organization_id=org_id,
        title="EU AI Act Internal Audit",
        framework_id=framework.id,
        auditor_name="Zach Warren",
        scope="AI literacy, prohibited practices and classification obligations.",
    )
    audit_state.apply_status(audit, "planned")
    db_session.add(audit)
    await db_session.flush()
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=user_id)
    await db_session.commit()

    items = list(
        (
            await db_session.execute(
                select(AuditItem).where(AuditItem.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "in_progress"}
    )
    for item in items:
        response = await client.post(
            f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
            json={"decision": "observation", "note": "Worth watching next cycle."},
        )
        assert response.status_code == 200, response.text

    done = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert done.status_code == 200, done.text

    detail = (await client.get(f"/api/v1/compliance/audits/{audit.id}")).json()
    progress = detail["progress"]
    # §4/§6: conclusions and remediation counted apart.
    assert progress["observations"] == len(items)
    assert progress["minor"] == progress["major"] == progress["critical"] == 0
    assert progress["remediation_open"] == len(items)
    assert progress["remediation_closed"] == 0
    assert detail["status"] == "completed"

    # §9: the work carries on, and the audit stays completed.
    finding_id = detail["findings"][0]["id"]
    await client.post(f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/ready")
    after = (await client.get(f"/api/v1/compliance/audits/{audit.id}")).json()
    assert after["status"] == "completed"
    assert after["progress"]["remediation_ready"] == 1

    verified = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/verify",
        json={"note": "New training records demonstrate implementation."},
    )
    assert verified.status_code == 200, verified.text
    final = (await client.get(f"/api/v1/compliance/audits/{audit.id}")).json()
    assert final["status"] == "completed"
    assert final["progress"]["remediation_closed"] == 1


@pytest.mark.anyio
async def test_a_minor_finding_needs_an_owner_before_the_audit_completes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8's middle rule. An open minor with nothing behind it is a note."""
    user_id, org_id = await _signup_full(
        client, f"min-{uuid.uuid4().hex[:6]}@example.com", "Minor Org"
    )
    framework = await _framework(db_session, "iso27001")
    audit = Audit(
        organization_id=org_id,
        title="ISO 27001 Internal Audit",
        framework_id=framework.id,
        scope="Information security management system governance and controls.",
    )
    audit_state.apply_status(audit, "planned")
    db_session.add(audit)
    await db_session.flush()
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=user_id)
    await db_session.commit()

    items = list(
        (
            await db_session.execute(
                select(AuditItem).where(AuditItem.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "in_progress"}
    )
    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{items[0].id}/decision",
        json={"decision": "minor", "note": "Documented late."},
    )
    for item in items[1:]:
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
            json={"decision": "no_finding"},
        )

    # Recording a minor finding attaches remediation, so the normal flow
    # already satisfies the rule.
    finding = (
        await db_session.execute(
            select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        )
    ).scalars().one()
    assert finding.severity == "medium"
    assert finding.related_task_id is not None, "a minor finding gets a home"

    # Strip the work to reach the state the rule exists for — a finding
    # from before this behaviour, or one whose task was removed.
    finding.related_task_id = None
    await db_session.commit()

    blocked = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert blocked.status_code == 422
    assert "no remediation attached" in blocked.json()["error"]["message"]

    # Give it an owner and it completes, with the finding still open.
    task = Task(
        organization_id=org_id,
        title="Document the control",
        module="compliance",
        status="open",
    )
    db_session.add(task)
    await db_session.flush()
    finding.related_task_id = task.id
    await db_session.commit()

    done = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert done.status_code == 200, done.text
    assert finding.status != "closed", "the audit completed; the work did not"


# --- §2/§3/§20 scope transparency --------------------------------------


@pytest.mark.anyio
async def test_the_scope_explains_every_absence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2/§20: "3 in scope" is not an answer without the other fifteen."""
    user_id, org_id = await _signup_full(
        client, f"scp-{uuid.uuid4().hex[:6]}@example.com", "Scope Org"
    )
    framework = await _framework(db_session, "gdpr")
    audit = Audit(
        organization_id=org_id,
        title="GDPR Internal Audit",
        framework_id=framework.id,
        scope="Privacy governance, lawful processing and data subject rights.",
    )
    audit_state.apply_status(audit, "planned")
    db_session.add(audit)
    await db_session.flush()
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=user_id)
    await db_session.commit()

    scope = (await client.get(f"/api/v1/compliance/audits/{audit.id}/scope")).json()
    assert scope["included"] > 0
    assert len(scope["lines"]) == scope["included"] + scope["not_applicable"] + scope["excluded"]
    # Nothing is hidden, and every line says why it is where it is.
    for line in scope["lines"]:
        assert line["disposition"] in ("included", "not_applicable", "excluded")
        if line["disposition"] == "not_applicable":
            assert line["reason"], line["reference_code"]


@pytest.mark.anyio
async def test_excluding_a_requirement_needs_a_reason_and_changes_this_audit_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3: audit scope is not the organization's applicability."""
    user_id, org_id = await _signup_full(
        client, f"exc-{uuid.uuid4().hex[:6]}@example.com", "Exclude Org"
    )
    framework = await _framework(db_session, "gdpr")
    audit = Audit(
        organization_id=org_id,
        title="GDPR limited internal audit",
        framework_id=framework.id,
        scope="A limited review of processor management only.",
    )
    audit_state.apply_status(audit, "planned")
    db_session.add(audit)
    await db_session.flush()
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=user_id)
    await db_session.commit()

    items = list(
        (
            await db_session.execute(
                select(AuditItem).where(AuditItem.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    before = len(items)

    empty = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{items[0].id}/exclude",
        json={"reason": "   "},
    )
    assert empty.status_code == 422

    excluded = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{items[0].id}/exclude",
        json={"reason": "Outside the scope of this limited internal audit."},
    )
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["excluded_at"] is not None
    assert "limited internal audit" in excluded.json()["exclusion_reason"]

    # Out of the worklist, still in the scope view with its reason.
    listed = (await client.get(f"/api/v1/compliance/audits/{audit.id}/items")).json()
    assert len(listed) == before - 1

    scope = (await client.get(f"/api/v1/compliance/audits/{audit.id}/scope")).json()
    assert scope["excluded"] == 1
    line = next(l for l in scope["lines"] if l["disposition"] == "excluded")
    assert "limited internal audit" in line["reason"]

    # The organization's applicability is untouched: preparing again
    # still evaluates the same requirements.
    report = await audit_workspace.prepare(
        db_session, audit=audit, actor_user_id=user_id
    )
    assert report.applicable == before

    # And putting it back restores it.
    restored = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{items[0].id}/include"
    )
    assert restored.status_code == 200
    assert restored.json()["excluded_at"] is None


@pytest.mark.anyio
async def test_a_decided_requirement_cannot_be_excluded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A finding against something the report says was never examined."""
    user_id, org_id = await _signup_full(
        client, f"dec-{uuid.uuid4().hex[:6]}@example.com", "Decided Org"
    )
    framework = await _framework(db_session, "iso42001")
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        framework_id=framework.id,
        scope="AI governance, risk management and lifecycle controls.",
    )
    audit_state.apply_status(audit, "planned")
    db_session.add(audit)
    await db_session.flush()
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=user_id)
    await db_session.commit()

    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "in_progress"}
    )
    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
        json={"decision": "observation", "note": "Noted."},
    )

    refused = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/exclude",
        json={"reason": "Changed my mind about the scope."},
    )
    assert refused.status_code == 422
    assert "already has an auditor conclusion" in refused.json()["error"]["message"]


# --- §19 a scope statement has to say something ------------------------


@pytest.mark.anyio
async def test_a_placeholder_scope_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reported audit's scope read "This is"."""
    await _signup_full(client, f"txt-{uuid.uuid4().hex[:6]}@example.com", "Text Org")

    refused = await client.post(
        "/api/v1/compliance/audits",
        json={"title": "EU AI Act Internal Audit", "scope": "This is"},
    )
    assert refused.status_code == 422

    accepted = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "EU AI Act Internal Audit",
            "scope": (
                "AI literacy, prohibited practices, AI-system classification "
                "and governance obligations."
            ),
        },
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["scope"].startswith("AI literacy")
