"""The completed audit's last step: preview it, read it, then issue it.

A completed audit used to end at 18/18 reviewed with nowhere to go. The
report was the missing half — and the half where getting it wrong is
irreversible, because an audit report is a statement somebody puts their
name to and may circulate.

So the rules these pin are the ones that make it safe to issue:

- **Preview writes nothing.** Opening one, reading it and walking away
  leaves no file, no record and no audit-log event. Otherwise the
  history is a list of reports somebody considered.
- **Generation issues what was read.** The preview returns a digest;
  generating requires it back and refuses if the audit moved in between.
- **A report is never edited.** Remediation moves, version 1 keeps
  saying what it said, and version 2 says the new thing.
- **The conclusion and the remediation are different clocks.** "Minor
  finding" is what the auditor decided; "Closed" is where the work
  stands. A report showing one of them is wrong in a different way each
  time.

And the count that started this: an audit with 18 conclusions reported
19 findings, because an auditor who verified an observation and then
revised that conclusion left two findings on one requirement. Both are
real. Only one is live.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance import audit_report, audit_report_service, audit_state
from app.compliance.audit_findings import record_decision, verify_and_close
from app.compliance.audit_render import render_audit_report_pdf
from app.compliance.models import (
    Audit,
    AuditFinding,
    AuditItem,
    AuditReport,
    Framework,
    Policy,
    Requirement,
)
from app.core.models import Task
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


_CLAUSES = [
    ("4.1", "Understanding the organization and its context"),
    ("4.2", "Understanding the needs and expectations of interested parties"),
    ("6.1", "Actions to address risks and opportunities"),
    ("9.2", "Internal audit"),
]


async def _framework(db: AsyncSession) -> Framework:
    framework = (
        await db.execute(select(Framework).where(Framework.key == "iso42001"))
    ).scalars().first()
    if framework is None:
        framework = Framework(key="iso42001", name="ISO 42001", description=None)
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
    for code, title in _CLAUSES:
        if code not in existing:
            db.add(
                Requirement(
                    framework_id=framework.id,
                    reference_code=code,
                    title=title,
                    description=None,
                )
            )
    await db.flush()
    return framework


async def _audit_with_items(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    status: str = "completed",
    decisions: list[str] | None = None,
) -> tuple[Audit, list[AuditItem]]:
    """A prepared audit with one item per clause, decided as asked.

    Built directly rather than through `prepare`, so the state under
    test is stated here: these conclusions, this evidence, this status.
    """
    framework = await _framework(db)
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        framework_id=framework.id,
        framework_name=framework.name,
        auditor_name="Zach Warren",
        # A colleague running an internal audit, recorded as such. The
        # alternative — leaving it unset and letting the report infer —
        # is exactly the bug  covers.
        auditor_type="internal",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, status)
    db.add(audit)
    await db.flush()

    requirements = (
        await db.execute(
            select(Requirement).where(Requirement.framework_id == framework.id)
        )
    ).scalars().all()
    by_code = {r.reference_code: r for r in requirements}

    items: list[AuditItem] = []
    for index, (code, title) in enumerate(_CLAUSES):
        item = AuditItem(
            organization_id=org_id,
            audit_id=audit.id,
            requirement_id=by_code[code].id,
            reference_code=code,
            requirement_title=title,
            framework_key="iso42001",
            control_title=f"Control for {code}",
            prepared_status="evidenced" if index % 2 == 0 else "no_evidence",
            prepared_confidence=80,
            prepared_why="Evidence on file supports this requirement.",
            prepared_missing=None if index % 2 == 0 else "No evidence attached.",
            evidence_snapshot=(
                [
                    {
                        "evidence_id": str(uuid.uuid4()),
                        "file_id": str(uuid.uuid4()),
                        "title": "AI Governance Policy.docx",
                        "filename": "AI Governance Policy.docx",
                        "document_href": None,
                    }
                ]
                if index % 2 == 0
                else []
            ),
        )
        db.add(item)
        items.append(item)
    await db.flush()

    if decisions:
        for item, decision in zip(items, decisions, strict=False):
            await record_decision(
                db,
                audit=audit,
                item=item,
                decision=decision,
                note="Recorded during the audit." if decision != "no_finding" else None,
                actor_user_id=None,
            )
    await db.flush()
    return audit, items


# --- §2/§3 what the preview says ---------------------------------------


@pytest.mark.asyncio
async def test_the_preview_carries_every_section_the_report_needs(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "report1@example.com", "Report One")
    audit, _ = await _audit_with_items(
        db_session,
        org_id,
        decisions=["minor", "observation", "no_finding", "major"],
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)

    assert preview.audit_title == "ISO 42001 Internal Audit"
    assert preview.framework_name == "ISO 42001"
    assert preview.auditor_name == "Zach Warren"
    assert preview.scope
    assert preview.completed_at is not None
    assert preview.progress.scoped == 4
    assert preview.progress.reviewed == 4
    assert preview.progress.percent_reviewed == 100
    # Conclusions in the auditor's words, counted by what was decided.
    assert preview.conclusion_counts == {
        "Minor finding": 1,
        "Observation": 1,
        "No finding": 1,
        "Major finding": 1,
    }
    # Findings worst first, and `no_finding` raised none. Major and
    # critical share a group: an executive treats them the same way, and
    # two near-empty sections at the top of a report is worse than one.
    assert [group.label for group in preview.findings_by_severity] == [
        "Major and critical findings",
        "Minor findings",
        "Observations",
    ]
    assert len(preview.findings) == 3
    assert preview.evidence_index
    assert preview.limitations
    assert preview.disclaimer.startswith("This report represents an internal audit")
    assert "not an independent certification or legal opinion" in preview.disclaimer
    assert preview.next_version == 1
    assert preview.ready


@pytest.mark.asyncio
async def test_the_conclusion_and_the_remediation_are_different_clocks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3: "Audit conclusion: Minor finding / Current remediation: Closed".

    The conclusion came from a person and cannot move. The remediation
    is live. Collapsing them either erases the finding that was raised
    or pretends nothing has been fixed since.
    """
    org_id = await _signup(client, "report2@example.com", "Report Two")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["minor", "no_finding", "no_finding", "no_finding"]
    )
    finding = await db_session.get(AuditFinding, items[0].finding_id)
    assert finding is not None
    await verify_and_close(
        db_session,
        finding=finding,
        note="A quarterly record now demonstrates the process operating.",
        actor_user_id=None,
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    line = next(c for c in preview.conclusions if c.reference_code == "4.1")

    assert line.decision_label == "Minor finding"
    assert line.current_remediation_label == "Closed"
    # And the finding says the same thing from its own side.
    reported = next(f for f in preview.findings if f.reference_code == "4.1")
    assert reported.conclusion_label == "Minor finding"
    assert reported.current_status_label == "Closed"
    assert reported.verification_note


@pytest.mark.asyncio
async def test_the_preview_does_not_rebuild_conclusions_from_current_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3: historical conclusions are read, never re-derived.

    The evidence state moves after the audit — that is the normal case,
    not the edge one. What the auditor concluded does not move with it.
    """
    org_id = await _signup(client, "report3@example.com", "Report Three")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["major", "no_finding", "no_finding", "no_finding"]
    )
    await db_session.commit()

    # Somebody attaches evidence and the control is reassessed clean.
    items[0].prepared_status = "evidenced"
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    line = next(c for c in preview.conclusions if c.reference_code == "4.1")
    assert line.decision_label == "Major finding"
    assert len(preview.findings) == 1


# --- §9 the count that did not reconcile --------------------------------


@pytest.mark.asyncio
async def test_a_revised_conclusion_leaves_one_live_finding_not_two(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: 18 conclusions reported 19 findings, and this is why.

    The auditor recorded an observation, verified and closed it, and
    then revised the conclusion on that same requirement. A closed
    verification is somebody's signature and must not be reopened, so a
    fresh finding is raised — correctly. What was missing was any mark
    on the first one saying it had been replaced.
    """
    org_id = await _signup(client, "report4@example.com", "Report Four")
    audit, items = await _audit_with_items(
        db_session,
        org_id,
        status="in_progress",
        decisions=["observation", "no_finding", "no_finding", "no_finding"],
    )
    original = await db_session.get(AuditFinding, items[0].finding_id)
    assert original is not None
    await verify_and_close(
        db_session,
        finding=original,
        note="Closed after review.",
        actor_user_id=None,
    )
    await db_session.commit()

    # The auditor changes their mind.
    result = await record_decision(
        db_session,
        audit=audit,
        item=items[0],
        decision="minor",
        note="On reflection this is a minor nonconformity, not an observation.",
        actor_user_id=None,
    )
    await db_session.commit()

    assert result.finding_created
    assert result.superseded is not None
    assert result.superseded.id == original.id

    # Both rows are still there. Nothing about the first was rewritten.
    rows = (
        await db_session.execute(
            select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        )
    ).scalars().all()
    assert len(rows) == 2
    await db_session.refresh(original)
    assert original.status == "closed"
    assert original.severity == "low"
    assert original.verified_at is not None
    assert original.superseded_at is not None
    assert original.superseded_by_id == result.finding.id

    # And the counts reconcile: one conclusion, one live finding.
    audit_state.apply_status(audit, "completed")
    await db_session.commit()
    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.progress.findings == 1
    assert preview.progress.superseded == 1
    assert len(preview.superseded_findings) == 1
    assert preview.superseded_findings[0].superseded_reason
    assert any("replaced" in line for line in preview.limitations)


@pytest.mark.asyncio
async def test_a_conclusion_with_no_finding_also_supersedes_the_closed_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The other shape: revised to a conclusion that raises nothing.

    The row points at no finding afterwards, so a closed finding was
    left dangling with nothing marking it either.
    """
    org_id = await _signup(client, "report5@example.com", "Report Five")
    audit, items = await _audit_with_items(
        db_session,
        org_id,
        status="in_progress",
        decisions=["minor", "no_finding", "no_finding", "no_finding"],
    )
    original = await db_session.get(AuditFinding, items[0].finding_id)
    await verify_and_close(
        db_session,
        finding=original,
        note="Closed after review.",
        actor_user_id=None,
    )
    await db_session.commit()

    await record_decision(
        db_session,
        audit=audit,
        item=items[0],
        decision="no_finding",
        note=None,
        actor_user_id=None,
    )
    await db_session.commit()

    await db_session.refresh(original)
    assert original.status == "closed"
    assert original.superseded_at is not None
    assert items[0].finding_id is None


# --- §7 the cancel test --------------------------------------------------


@pytest.mark.asyncio
async def test_previewing_writes_nothing_at_all(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§7: open the preview, close it, and nothing happened.

    No PDF, no report record, no audit-log event. A preview that left a
    trace would make the history a log of things considered rather than
    things issued.
    """
    org_id = await _signup(client, "report6@example.com", "Report Six")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()

    before = len(
        (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )

    response = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report/preview"
    )
    assert response.status_code == 200, response.text
    await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")

    reports = (
        await db_session.execute(
            select(AuditReport).where(AuditReport.audit_id == audit.id)
        )
    ).scalars().all()
    assert reports == []

    after = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.organization_id == org_id)
        )
    ).scalars().all()
    assert len(after) == before
    assert not any(
        event.action.startswith("compliance.audit_report") for event in after
    )


@pytest.mark.asyncio
async def test_an_unfinished_audit_cannot_be_reported_on(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A report of an audit still in progress states conclusions the
    auditor has not finished reaching."""
    org_id = await _signup(client, "report7@example.com", "Report Seven")
    audit, _ = await _audit_with_items(
        db_session, org_id, status="in_progress", decisions=["observation"]
    )
    await db_session.commit()

    preview = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report/preview"
    )
    body = preview.json()
    assert body["ready"] is False
    assert body["blockers"][0]["code"] == "audit_not_completed"

    refused = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": body["digest"]},
    )
    assert refused.status_code == 422
    assert "not complete" in refused.text


# --- §5/§6 generation, and versions -------------------------------------


@pytest.mark.asyncio
async def test_generating_issues_what_was_previewed_and_records_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "report8@example.com", "Report Eight")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["minor", "observation", "no_finding", "major"]
    )
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    response = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": preview["digest"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version"] == 1
    assert body["file_format"] == "pdf"
    assert body["file_id"]
    assert body["generated_by_name"] == "Zach Warren"
    assert body["requirements_reviewed"] == 4
    assert body["findings_count"] == 3
    assert body["stale"] is False

    report = await db_session.get(AuditReport, uuid.UUID(body["id"]))
    assert report is not None
    contents = report.contents
    # §5: everything the record has to keep.
    assert contents["audit_id"] == str(audit.id)
    assert contents["framework_name"] == "ISO 42001"
    assert contents["progress"]["reviewed"] == 4
    assert len(contents["conclusions"]) == 4
    assert len(contents["findings"]) == 3
    assert contents["findings"][0]["status_at_generation"]
    assert contents["evidence_index"]
    assert contents["disclaimer"]
    assert report.source_digest == preview["digest"]
    assert report.generated_at is not None

    event = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "compliance.audit_report.generated"
            )
        )
    ).scalars().first()
    assert event is not None
    assert event.after_state["version"] == 1
    assert event.after_state["findings_by_severity"]


@pytest.mark.asyncio
async def test_generation_refuses_a_preview_the_audit_has_moved_past(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Between reading a preview and clicking generate, a colleague can
    close a finding. Without the digest, the person confirming would be
    putting their name to a document they never saw."""
    org_id = await _signup(client, "report9@example.com", "Report Nine")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["minor", "no_finding", "no_finding", "no_finding"]
    )
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()

    finding = await db_session.get(AuditFinding, items[0].finding_id)
    await verify_and_close(
        db_session,
        finding=finding,
        note="Closed while the preview was open.",
        actor_user_id=None,
    )
    await db_session.commit()

    refused = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": preview["digest"]},
    )
    assert refused.status_code == 422
    assert "changed since" in refused.text


@pytest.mark.asyncio
async def test_a_later_version_never_edits_the_earlier_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: remediation moves; version 1 keeps saying what it said."""
    org_id = await _signup(client, "report10@example.com", "Report Ten")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["minor", "no_finding", "no_finding", "no_finding"]
    )
    await db_session.commit()

    first = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    v1 = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": first["digest"]},
        )
    ).json()
    v1_contents = (
        await db_session.get(AuditReport, uuid.UUID(v1["id"]))
    ).contents
    assert v1_contents["findings"][0]["status_at_generation"] != "closed"

    finding = await db_session.get(AuditFinding, items[0].finding_id)
    await verify_and_close(
        db_session,
        finding=finding,
        note="Remediated and verified after the report went out.",
        actor_user_id=None,
    )
    await db_session.commit()

    listed = (
        await client.get(f"/api/v1/compliance/audits/{audit.id}/reports")
    ).json()
    assert len(listed) == 1
    assert listed[0]["stale"] is True

    second = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    assert second["next_version"] == 2
    v2 = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": second["digest"]},
        )
    ).json()
    assert v2["version"] == 2

    # Version 1 is byte-for-byte what it was.
    reloaded = await db_session.get(AuditReport, uuid.UUID(v1["id"]))
    await db_session.refresh(reloaded)
    assert reloaded.contents == v1_contents
    assert reloaded.version == 1

    v2_contents = (await db_session.get(AuditReport, uuid.UUID(v2["id"]))).contents
    assert v2_contents["findings"][0]["status_at_generation"] == "closed"

    history = (
        await client.get(f"/api/v1/compliance/audits/{audit.id}/reports")
    ).json()
    assert [row["version"] for row in history] == [2, 1]
    assert history[0]["stale"] is False


@pytest.mark.asyncio
async def test_a_generated_report_is_downloadable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "report11@example.com", "Report Eleven")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    report = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": preview["digest"]},
        )
    ).json()

    response = await client.get(
        f"/api/v1/compliance/audits/{audit.id}/reports/{report['id']}/download"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"]
    assert body["filename"].endswith(".pdf")
    assert "v1" in body["filename"]


@pytest.mark.asyncio
async def test_a_report_from_another_organization_is_not_reachable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "report12@example.com", "Report Twelve")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()
    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    report = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": preview["digest"]},
        )
    ).json()

    await _signup(client, "report13@example.com", "Report Thirteen")
    assert (
        await client.get(f"/api/v1/compliance/audits/{audit.id}/reports")
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/compliance/audits/{audit.id}/reports/{report['id']}/download"
        )
    ).status_code == 404


# --- the rendered document ----------------------------------------------


@pytest.mark.asyncio
async def test_the_pdf_renders_from_the_preview_and_nothing_else(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "report14@example.com", "Report Fourteen")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["critical", "observation", "minor", "no_finding"]
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    payload = render_audit_report_pdf(preview)
    assert payload.startswith(b"%PDF-")
    assert len(payload) > 3000


@pytest.mark.asyncio
async def test_an_audit_with_no_findings_still_produces_a_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A clean audit is a result, not an empty page."""
    org_id = await _signup(client, "report15@example.com", "Report Fifteen")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["no_finding"] * 4
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.findings == []
    assert preview.conclusion_counts == {"No finding": 4}
    assert preview.ready
    assert render_audit_report_pdf(preview).startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_the_limitations_name_what_the_report_does_not_cover(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: a document that states only its findings overstates its reach."""
    org_id = await _signup(client, "report16@example.com", "Report Sixteen")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["observation", "observation", "observation"]
    )
    # One requirement never reviewed, one taken out of scope.
    items[3].decision = None
    items[2].excluded_at = items[0].decided_at
    items[2].exclusion_reason = "Not applicable to this engagement."
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    joined = " ".join(preview.limitations)
    assert "excluded from scope" in joined
    assert "no auditor conclusion" in joined
    assert "no evidence on file" in joined
    assert "may have been superseded" in joined


@pytest.mark.asyncio
async def test_the_digest_moves_only_when_the_report_would_say_something_new(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A fingerprint that changed on every unrelated write would report
    every audit as stale, and the notice would stop meaning anything."""
    org_id = await _signup(client, "report17@example.com", "Report Seventeen")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["minor", "no_finding", "no_finding", "no_finding"]
    )
    await db_session.commit()

    before = await audit_report.current_digest(db_session, audit=audit)
    assert await audit_report.current_digest(db_session, audit=audit) == before

    # A snapshot field a reader never sees does not move it.
    items[1].prepared_why = "Reworded explanation."
    await db_session.commit()
    assert await audit_report.current_digest(db_session, audit=audit) == before

    # A conclusion does.
    await record_decision(
        db_session,
        audit=audit,
        item=items[1],
        decision="observation",
        note="Noted.",
        actor_user_id=None,
    )
    await db_session.commit()
    assert await audit_report.current_digest(db_session, audit=audit) != before


@pytest.mark.asyncio
async def test_report_refused_is_raised_rather_than_a_half_written_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "report18@example.com", "Report Eighteen")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()
    preview = await audit_report.build_preview(db_session, audit=audit)

    with pytest.raises(audit_report_service.ReportRefused):
        await audit_report_service.generate(
            db_session,
            audit=audit,
            preview=preview,
            confirm_digest="not-the-digest",
            actor_user_id=None,
        )

    assert (
        await db_session.execute(
            select(AuditReport).where(AuditReport.audit_id == audit.id)
        )
    ).scalars().all() == []


# =====================================================================
# The report as a deliverable, not a data dump
# =====================================================================
#
# The generated PDF was structurally right and read like application
# output: findings headed with the diagnostic sentence that explained the
# evidence state, a requirement table column called "Now", an evidence
# index whose version column was a dash, and no executive summary at all.
#
# These pin the presentation, which for a document people circulate is
# not cosmetic: a finding titled "1 document(s) are mapped to this
# requirement, but Veyntra has no itemised expectation set for it yet" is
# Veyntra explaining its own limits, presented as the auditor's result.


def _pdf_text(payload: bytes) -> str:
    """The rendered text, for assertions about what a reader sees."""
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _pdf_pages(payload: bytes) -> int:
    from io import BytesIO

    from pypdf import PdfReader

    return len(PdfReader(BytesIO(payload)).pages)


@pytest.mark.asyncio
async def test_the_executive_summary_states_the_result_in_sentences(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2: page one answers "what happened" before any table."""
    org_id = await _signup(client, "quality1@example.com", "Quality One")
    audit, _ = await _audit_with_items(
        db_session,
        org_id,
        decisions=["observation", "observation", "no_finding", "minor"],
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    summary = " ".join(preview.executive_summary)

    assert "assessed 4 ISO 42001 requirements within the defined scope" in summary
    assert "All 4 were reviewed" in summary
    assert "2 observations" in summary
    assert "1 minor finding" in summary
    # §2: the absent severities are a result too.
    assert "No major or critical findings were raised" in summary
    assert "1 requirement was concluded with no finding" in summary
    assert "At the time this report was generated, remediation stood at" in summary

    # And the metric block carries every conclusion with its zeros.
    labels = {metric.label: metric.value for metric in preview.metrics}
    assert labels["Requirements reviewed"] == "4 / 4"
    assert labels["No finding"] == "1"
    assert labels["Observation"] == "2"
    assert labels["Minor finding"] == "1"
    assert labels["Major finding"] == "0"
    assert labels["Critical finding"] == "0"


@pytest.mark.asyncio
async def test_a_clean_audit_says_so_rather_than_printing_empty_sections(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: "No audit findings were recorded", not a blank heading."""
    org_id = await _signup(client, "quality2@example.com", "Quality Two")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["no_finding"] * 4
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.findings == []
    assert preview.findings_by_severity == []
    assert "The auditor recorded no findings." in preview.executive_summary[1]

    text = _pdf_text(render_audit_report_pdf(preview))
    assert "No audit findings were recorded." in text
    assert "No remediation items were opened by this audit." in text
    assert (
        "No findings had been verified and closed as of the report generation date."
        in text.replace("\n", " ")
    )
    # §10: no empty severity headings.
    assert "Major and critical findings" not in text
    assert "Minor findings" not in text


@pytest.mark.asyncio
async def test_findings_are_grouped_worst_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: major and critical, then minor, then observations."""
    org_id = await _signup(client, "quality3@example.com", "Quality Three")
    audit, _ = await _audit_with_items(
        db_session,
        org_id,
        decisions=["observation", "critical", "minor", "major"],
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert [group.key for group in preview.findings_by_severity] == [
        "major_critical",
        "minor",
        "observations",
    ]
    assert preview.findings_by_severity[0].count == 2
    assert [line.severity for line in preview.findings] == [
        "critical",
        "high",
        "medium",
        "low",
    ]

    text = _pdf_text(render_audit_report_pdf(preview))
    assert text.index("Major and critical findings") < text.index("Minor findings")
    assert text.index("Minor findings") < text.index("Observations")


@pytest.mark.asyncio
async def test_the_requirement_is_the_subject_not_the_diagnostic(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3/§4: the reported problem, at both ends.

    A finding used to be titled with `prepared_missing`, which is
    sometimes a real gap and sometimes Veyntra describing its own limits.
    Now the requirement heads the block, the diagnostic becomes a
    report-grade sentence under "Veyntra assessment", and the stored
    title is not the heading.
    """
    org_id = await _signup(client, "quality4@example.com", "Quality Four")
    audit, items = await _audit_with_items(
        db_session, org_id, status="in_progress"
    )
    plumbing = (
        "1 document(s) are mapped to this requirement, but Veyntra has no "
        "itemised expectation set for it yet, so it cannot confirm on its own "
        "that they cover it in full"
    )
    items[0].prepared_status = "needs_review"
    items[0].prepared_missing = plumbing
    await db_session.flush()

    # §4: a new finding is not named after the diagnostic.
    await record_decision(
        db_session,
        audit=audit,
        item=items[0],
        decision="observation",
        note=None,
        actor_user_id=None,
    )
    audit_state.apply_status(audit, "completed")
    await db_session.commit()

    finding = await db_session.get(AuditFinding, items[0].finding_id)
    assert finding.title.startswith("Observation: Understanding the organization")
    assert plumbing not in finding.title

    preview = await audit_report.build_preview(db_session, audit=audit)
    line = preview.findings[0]
    assert line.reference_code == "4.1"
    assert line.requirement_title == "Understanding the organization and its context"
    assert line.evidence_state_label == "Needs human verification"
    # §3: the preferred wording, derived rather than quoted.
    assert line.assessment == (
        "One document is mapped to this requirement, but the available "
        "evidence does not allow Veyntra to verify full coverage."
    )
    # The plumbing sentence is nowhere in the rendered document.
    text = _pdf_text(render_audit_report_pdf(preview))
    assert "itemised expectation set" not in text
    assert "4.1 — Understanding the organization and its context" in text.replace(
        "\n", " "
    )


@pytest.mark.asyncio
async def test_a_specific_gap_survives_as_its_own_line(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The other half of §3: not all of `prepared_missing` is plumbing.

    "The approved AI policy" is exactly what an auditor needs. It moves
    to its own labelled line rather than being thrown away with the
    diagnostic prose.
    """
    org_id = await _signup(client, "quality5@example.com", "Quality Five")
    audit, items = await _audit_with_items(
        db_session, org_id, status="in_progress"
    )
    items[0].prepared_status = "deficient"
    items[0].prepared_missing = "The approved AI policy"
    await db_session.flush()
    await record_decision(
        db_session,
        audit=audit,
        item=items[0],
        decision="minor",
        note="The policy is drafted but not approved.",
        actor_user_id=None,
    )
    audit_state.apply_status(audit, "completed")
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    line = preview.findings[0]
    assert line.not_evidenced == "The approved AI policy"
    assert line.auditor_note == "The policy is drafted but not approved."

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Not evidenced" in text
    assert "The approved AI policy" in text
    assert "Auditor note" in text


@pytest.mark.asyncio
async def test_satisfied_evidence_with_a_finding_never_reads_as_a_contradiction(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the case the real report had two of.

    Veyntra assessed the evidence as satisfying the requirement and the
    auditor concluded an Observation anyway. Legitimate — an auditor may
    see what the record does not — but printed side by side with nothing
    between them it reads as a defect in the report.
    """
    org_id = await _signup(client, "quality6@example.com", "Quality Six")
    audit, items = await _audit_with_items(
        db_session, org_id, status="in_progress"
    )
    items[0].prepared_status = "evidenced"
    items[1].prepared_status = "evidenced"
    await db_session.flush()

    # One with a reason, one without.
    await record_decision(
        db_session,
        audit=audit,
        item=items[0],
        decision="minor",
        note=(
            "The documented control exists, but evidence of consistent "
            "operational execution was not available."
        ),
        actor_user_id=None,
    )
    await record_decision(
        db_session,
        audit=audit,
        item=items[1],
        decision="observation",
        note=None,
        actor_user_id=None,
    )
    audit_state.apply_status(audit, "completed")
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    explained = next(f for f in preview.findings if f.reference_code == "4.1")
    unexplained = next(f for f in preview.findings if f.reference_code == "4.2")

    assert explained.auditor_note and not explained.rationale_gap
    # §6: nobody wrote a reason, so the report says that rather than
    # inventing one or leaving the reader to spot the mismatch.
    assert unexplained.auditor_note is None
    assert unexplained.rationale_gap is True

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "evidence of consistent operational execution was not available" in text
    assert "No rationale was recorded for this conclusion." in text


@pytest.mark.asyncio
async def test_remediation_carries_owner_and_due_date_where_they_exist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11/§12: only real fields. Unassigned is said, not blank."""
    org_id = await _signup(client, "quality7@example.com", "Quality Seven")
    audit, items = await _audit_with_items(
        db_session,
        org_id,
        decisions=["major", "no_finding", "no_finding", "no_finding"],
    )
    finding = await db_session.get(AuditFinding, items[0].finding_id)
    assert finding.related_task_id is not None
    task = await db_session.get(Task, finding.related_task_id)
    owner = (
        await db_session.execute(select(User).where(User.email == "quality7@example.com"))
    ).scalars().first()
    task.assignee_id = owner.id
    task.due_at = datetime(2026, 9, 20, tzinfo=UTC)
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    line = preview.findings[0]
    assert line.remediation_owner == "Zach Warren"
    assert line.remediation_due == datetime(2026, 9, 20, tzinfo=UTC)
    assert preview.remediation_rows[0].id == line.id

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Zach Warren" in text
    assert "September 20, 2026" in text or "Sep 20, 2026" in text


@pytest.mark.asyncio
async def test_the_evidence_index_reports_the_version_reviewed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16/§17: the version relied on during the audit, not today's.

    The snapshot carries it, so revising the document afterwards cannot
    change what the report says was reviewed. A version nobody recorded
    is named as such rather than printed as a dash.
    """
    org_id = await _signup(client, "quality8@example.com", "Quality Eight")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    # One document whose version preparation captured, one it did not.
    items[0].evidence_snapshot = [
        {
            "evidence_id": str(uuid.uuid4()),
            "file_id": str(uuid.uuid4()),
            "title": "03_AI_Governance_Policy.docx",
            "filename": "03_AI_Governance_Policy.docx",
            "document_version": "2.0",
        }
    ]
    items[2].evidence_snapshot = [
        {
            "evidence_id": str(uuid.uuid4()),
            "file_id": str(uuid.uuid4()),
            "title": "99_Undated_Note.docx",
            "filename": "99_Undated_Note.docx",
        }
    ]
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    index = {line.title: line for line in preview.evidence_index}

    governance = index["03_AI_Governance_Policy.docx"]
    assert governance.version == "2.0"
    assert governance.version_label == "2.0"
    assert governance.version_source == "snapshot"
    assert governance.requirement_codes == ["4.1"]
    # §17: what Veyntra made of the requirement it supported.
    assert governance.evidence_states == ["Evidence on file"]

    undated = index["99_Undated_Note.docx"]
    assert undated.version is None
    assert undated.version_label == "Version not recorded"

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Version reviewed" in text
    assert "2.0" in text
    assert "Version not recorded" in text


@pytest.mark.asyncio
async def test_a_document_revised_after_the_audit_does_not_change_the_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16: "Do not accidentally show the current version."

    The snapshot wins over any live lookup, which is the whole reason the
    version is captured at preparation.
    """
    org_id = await _signup(client, "quality9@example.com", "Quality Nine")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    file_id = uuid.uuid4()
    items[0].evidence_snapshot = [
        {
            "evidence_id": str(uuid.uuid4()),
            "file_id": str(file_id),
            "title": "Information Security Policy",
            "document_version": "1.4",
        }
    ]
    # The document has since been re-filed at 3.0.
    db_session.add(
        Policy(
            organization_id=org_id,
            title="Information Security Policy",
            file_id=file_id,
            version="3.0",
        )
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    line = next(
        entry
        for entry in preview.evidence_index
        if entry.title == "Information Security Policy"
    )
    assert line.version == "1.4"
    assert "3.0" not in _pdf_text(render_audit_report_pdf(preview))


@pytest.mark.asyncio
async def test_verification_history_names_who_checked_what(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§14: a table with the substance, not an empty grid."""
    org_id = await _signup(client, "quality10@example.com", "Quality Ten")
    audit, items = await _audit_with_items(
        db_session,
        org_id,
        decisions=["minor", "no_finding", "no_finding", "no_finding"],
    )
    finding = await db_session.get(AuditFinding, items[0].finding_id)
    await verify_and_close(
        db_session,
        finding=finding,
        note="Quarterly review record now demonstrates the process operating.",
        actor_user_id=None,
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert len(preview.verification) == 1
    row = preview.verification[0]
    assert row.reference_code == "4.1"
    assert row.requirement_title
    assert row.verification_note

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Verification history" in text
    assert "Quarterly review record now demonstrates" in text


@pytest.mark.asyncio
async def test_the_appendix_column_is_named_rather_than_abbreviated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§15/§18: "Now" said nothing, and the table belongs at the back."""
    org_id = await _signup(client, "quality11@example.com", "Quality Eleven")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")

    assert "Appendix A — Requirement-by-requirement results" in text
    assert "Current remediation status" in text
    assert "Evidence state at audit" in text
    # The old header, and the collision it produced.
    assert "Auditor conclusionNow" not in text
    # §18: the appendix comes after the findings and the sign-off.
    assert text.index("5. Findings") < text.index("Appendix A")
    assert text.index("9. Auditor sign-off") < text.index("Appendix A")


@pytest.mark.asyncio
async def test_every_page_carries_the_footer_and_its_number(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§20/§21: a page that reaches a desk alone still identifies itself."""
    org_id = await _signup(client, "quality12@example.com", "Quality Twelve")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    payload = render_audit_report_pdf(preview)
    pages = _pdf_pages(payload)
    assert pages >= 2

    from io import BytesIO

    from pypdf import PdfReader

    for index, page in enumerate(PdfReader(BytesIO(payload)).pages, start=1):
        text = (page.extract_text() or "").replace("\n", " ")
        assert "Veyntra Internal Audit Report" in text
        assert "ISO 42001 Internal Audit" in text
        assert "Report v1" in text
        assert "Confidential" in text
        assert f"Page {index}" in text


@pytest.mark.asyncio
async def test_a_large_audit_paginates_without_losing_the_findings(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§18: the structure has to survive 50+ requirements.

    The reason the requirement table is an appendix: at this size it
    would otherwise push the findings past where anybody reads.
    """
    org_id = await _signup(client, "quality13@example.com", "Quality Thirteen")
    framework = await _framework(db_session)
    audit = Audit(
        organization_id=org_id,
        title="Large Internal Audit",
        framework_id=framework.id,
        framework_name=framework.name,
        auditor_name="Zach Warren",
        scope="Everything in scope for this engagement.",
    )
    audit_state.apply_status(audit, "in_progress")
    db_session.add(audit)
    await db_session.flush()

    # One requirement per row: `uq_audit_item_requirement` is what makes
    # preparing twice reconcile rather than duplicate, and a fixture that
    # reuses one row would be testing something the product forbids.
    requirements: list[Requirement] = []
    for index in range(60):
        requirement = Requirement(
            framework_id=framework.id,
            reference_code=f"LARGE-{index + 1}",
            title=f"Requirement number {index + 1}",
            description=None,
        )
        db_session.add(requirement)
        requirements.append(requirement)
    await db_session.flush()

    items: list[AuditItem] = []
    for index in range(60):
        item = AuditItem(
            organization_id=org_id,
            audit_id=audit.id,
            requirement_id=requirements[index].id,
            reference_code=f"{index // 10 + 1}.{index % 10 + 1}",
            requirement_title=f"Requirement number {index + 1}",
            framework_key="iso42001",
            control_title=f"Control {index + 1}",
            prepared_status="evidenced" if index % 3 else "no_evidence",
            evidence_snapshot=[],
        )
        db_session.add(item)
        items.append(item)
    await db_session.flush()

    # A realistic spread rather than 60 of one thing.
    for index, item in enumerate(items):
        decision = (
            "major"
            if index == 0
            else "minor"
            if index < 4
            else "observation"
            if index < 12
            else "no_finding"
        )
        await record_decision(
            db_session,
            audit=audit,
            item=item,
            decision=decision,
            note="Recorded during the audit." if decision != "no_finding" else None,
            actor_user_id=None,
        )
    audit_state.apply_status(audit, "completed")
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    assert preview.progress.scoped == 60
    assert preview.progress.reviewed == 60
    assert len(preview.findings) == 12
    assert len(preview.conclusions) == 60

    payload = render_audit_report_pdf(preview)
    assert _pdf_pages(payload) > 5
    text = _pdf_text(payload).replace("\n", " ")
    assert "Major and critical findings (1)" in text
    assert "Minor findings (3)" in text
    assert "Observations (8)" in text
    # Every requirement still reaches the appendix.
    assert "Requirement number 60" in text


@pytest.mark.asyncio
async def test_the_generated_pdf_leaks_no_identifiers_or_raw_chunks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: internal identifiers do not belong in a document that
    circulates, and neither does retrieval plumbing."""
    org_id = await _signup(client, "quality14@example.com", "Quality Fourteen")
    audit, items = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    items[0].evidence_snapshot = [
        {
            "evidence_id": str(uuid.uuid4()),
            "file_id": str(uuid.uuid4()),
            "title": "AI Governance Policy.docx",
            "document_version": "1.0",
            "source_location": "Section 4.2",
            "model_confidence": 0.91,
        }
    ]
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    text = _pdf_text(render_audit_report_pdf(preview))

    assert not re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text
    )
    assert "chunk" not in text.lower()
    assert "model_confidence" not in text
    assert "0.91" not in text


@pytest.mark.asyncio
async def test_the_sign_off_records_identities_and_never_a_signature(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: no formal approval exists in the product, so none is drawn."""
    org_id = await _signup(client, "quality15@example.com", "Quality Fifteen")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    sign_off = preview["sign_off"]
    # The auditor is a structured identity now, not a formatted name.
    assert sign_off["auditor"]["name"] == "Zach Warren"
    assert sign_off["auditor"]["auditor_type"] == "internal"
    assert sign_off["completed_at"]
    assert sign_off["report_version"] == 1
    assert sign_off["approved_by"] is None

    generated = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": preview["digest"]},
    )
    assert generated.status_code == 201
    stored = await db_session.get(AuditReport, uuid.UUID(generated.json()["id"]))
    # The person who pressed generate is on the record and in the PDF.
    assert stored.contents["sign_off"]["generated_by"] == "Zach Warren"
    assert stored.contents["sign_off"]["approved_by"] is None


@pytest.mark.asyncio
async def test_the_preview_and_the_generated_document_say_the_same_thing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§26: what somebody approved is what they receive.

    The PDF takes an `AuditReportPreview` and nothing else, so this
    checks the contract rather than re-deriving it: every heading, the
    summary sentences, and the numbers all appear in both.
    """
    org_id = await _signup(client, "quality16@example.com", "Quality Sixteen")
    audit, _ = await _audit_with_items(
        db_session,
        org_id,
        decisions=["observation", "minor", "no_finding", "major"],
    )
    await db_session.commit()

    body = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    generated = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": body["digest"]},
    )
    assert generated.status_code == 201

    preview = await audit_report.build_preview(db_session, audit=audit)
    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")

    for heading in (
        "1. Audit information",
        "2. Executive summary",
        "3. Scope and methodology",
        "4. Audit results summary",
        "5. Findings",
        "6. Remediation and verification",
        "7. Evidence index",
        "8. Known limitations",
        "9. Auditor sign-off",
        "Appendix A",
    ):
        assert heading in text, heading

    # The sentences the preview showed are the sentences in the document.
    for sentence in body["executive_summary"]:
        assert sentence.replace("  ", " ") in text

    # And every finding the preview listed is in it, by requirement.
    for finding in body["findings"]:
        assert finding["requirement_title"] in text
        assert finding["assessment"] in text

    # The stored snapshot agrees with both.
    stored = await db_session.get(AuditReport, uuid.UUID(generated.json()["id"]))
    assert stored.contents["executive_summary"] == body["executive_summary"]
    assert stored.contents["classification"] == body["classification"]
    assert len(stored.contents["findings"]) == len(body["findings"])


@pytest.mark.asyncio
async def test_methodology_states_what_veyntra_did_and_did_not_conclude(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: the three clarifications a reader needs to weigh the report."""
    org_id = await _signup(client, "quality17@example.com", "Quality Seventeen")
    audit, _ = await _audit_with_items(
        db_session, org_id, decisions=["observation"] * 4
    )
    await db_session.commit()

    preview = await audit_report.build_preview(db_session, audit=audit)
    methodology = " ".join(preview.methodology)

    assert "prepared from the requirements, controls, evidence" in methodology
    assert "recorded by the named auditor" in methodology
    # Evidence state is not an audit conclusion.
    assert "it is not an audit conclusion" in methodology
    # Missing evidence is not automatic failure.
    assert "does not by itself constitute a failed requirement" in methodology
    # Remediation moves afterwards.
    assert "Remediation continues after an audit closes" in methodology

    text = _pdf_text(render_audit_report_pdf(preview)).replace("\n", " ")
    assert "Methodology" in text
