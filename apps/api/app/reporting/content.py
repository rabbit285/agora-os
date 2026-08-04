"""Report content builders (spec §65). Each of the 14 named report types
reuses an existing module's own real, live-computed dashboard/analytics
function wherever one exists (Executive/Board -> Onboarding's readiness
score, Security Posture -> the Security Overview aggregate, Sales
Performance/Pipeline -> Sales Intelligence, Support Performance ->
Support Analytics, Automation ROI -> Automation Analytics) rather than
inventing a second, independently-drifting formula. The 6 report types
with no pre-existing aggregate (Compliance, GDPR, EU AI Act, AI
Inventory, Risk, Vendor, Audit Evidence Pack) query the relevant
Compliance-module tables directly, following the same
`compute_x(db, *, organization_id) -> ...` convention.

`ReportContent` is a deliberately generic, renderer-agnostic
intermediate representation (a title plus an ordered list of
heading+rows sections) so `app.reporting.rendering` can turn any report
type into any of the 4 export formats without each builder needing to
know anything about PDF/DOCX/XLSX/CSV layout.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.analytics import compute_workflow_analytics
from app.compliance.models import (
    DPIA,
    DSAR,
    AISystem,
    Audit,
    AuditFinding,
    Control,
    ControlMapping,
    DataTransfer,
    Evidence,
    Framework,
    ProcessingActivity,
    Requirement,
    Risk,
    Vendor,
    VendorAssessment,
)
from app.onboarding.service import compute_readiness
from app.sales.intelligence import compute_sales_intelligence
from app.sales.models import Account, Opportunity
from app.secops.service import get_security_overview
from app.support.analytics import compute_support_analytics


@dataclass
class ReportSection:
    heading: str
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReportContent:
    title: str
    generated_at: datetime
    sections: list[ReportSection]


async def _count(db: AsyncSession, stmt: Any) -> int:
    result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    return int(result.scalar_one())


async def _build_executive_business_ai(
    db: AsyncSession, organization_id: uuid.UUID
) -> ReportContent:
    readiness = await compute_readiness(db, organization_id=organization_id)
    dimensions = [
        readiness.compliance,
        readiness.security,
        readiness.sales_automation,
        readiness.support_automation,
        readiness.process_automation,
    ]
    return ReportContent(
        title="Executive Business AI Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Business AI Readiness by Dimension",
                [{"Dimension": d.label, "Readiness %": d.percent} for d in dimensions],
            ),
            ReportSection(
                "Top Improvement Opportunities",
                [{"Opportunity": o.title, "Detail": o.detail} for o in readiness.opportunities],
            ),
        ],
    )


async def _build_board(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    readiness = await compute_readiness(db, organization_id=organization_id)
    security = await get_security_overview(db, organization_id=organization_id)
    sales = await compute_sales_intelligence(db, organization_id=organization_id)
    support = await compute_support_analytics(db, organization_id=organization_id)
    automation = await compute_workflow_analytics(db, organization_id=organization_id)

    open_pipeline_value = sum(
        value
        for stage, value in sales["pipeline_value_by_stage"].items()
        if stage not in ("closed_won", "closed_lost")
    )
    summary_rows = [
        {"Metric": "Compliance Readiness %", "Value": readiness.compliance.percent},
        {"Metric": "Security Readiness %", "Value": readiness.security.percent},
        {"Metric": "Security Score", "Value": security.security_score},
        {"Metric": "Open Security Incidents", "Value": security.open_incidents},
        {"Metric": "Open Pipeline Value", "Value": round(open_pipeline_value, 2)},
        {"Metric": "Win Rate %", "Value": sales["win_rate_percent"]},
        {"Metric": "Open Support Tickets", "Value": support["open_tickets"]},
        {"Metric": "Average CSAT", "Value": support["average_csat"]},
        {"Metric": "Automation Runs (total)", "Value": automation["total_runs"]},
        {"Metric": "Automation Success Rate %", "Value": automation["success_rate_percent"]},
    ]
    return ReportContent(
        title="Board Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection("Company Snapshot", summary_rows),
            ReportSection(
                "Top Improvement Opportunities",
                [{"Opportunity": o.title, "Detail": o.detail} for o in readiness.opportunities],
            ),
        ],
    )


async def _build_compliance(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    status_result = await db.execute(
        select(Control.status, func.count())
        .where(Control.organization_id == organization_id)
        .group_by(Control.status)
    )
    controls_rows = [{"Status": s, "Count": c} for s, c in status_result.all()]

    frameworks = list((await db.execute(select(Framework).order_by(Framework.name))).scalars().all())
    framework_rows = []
    for fw in frameworks:
        total_requirements = await _count(
            db, select(Requirement.id).where(Requirement.framework_id == fw.id)
        )
        if total_requirements == 0:
            continue
        covered = await _count(
            db,
            select(func.distinct(ControlMapping.requirement_id))
            .select_from(ControlMapping)
            .join(Control, Control.id == ControlMapping.control_id)
            .join(Requirement, Requirement.id == ControlMapping.requirement_id)
            .where(
                Requirement.framework_id == fw.id,
                Control.organization_id == organization_id,
                Control.status == "implemented",
            ),
        )
        framework_rows.append(
            {
                "Framework": fw.name,
                "Requirements": total_requirements,
                "Covered": covered,
                "Coverage %": round(100 * covered / total_requirements, 1),
            }
        )

    return ReportContent(
        title="Compliance Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection("Controls by Status", controls_rows),
            ReportSection("Framework Coverage", framework_rows),
        ],
    )


async def _build_security_posture(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    overview = await get_security_overview(db, organization_id=organization_id)
    rows = [
        {"Metric": "Security Score", "Value": overview.security_score},
        {"Metric": "Critical Alerts (open)", "Value": overview.critical_alerts},
        {"Metric": "High Risks (open)", "Value": overview.high_risks},
        {"Metric": "Assets Monitored", "Value": overview.assets_monitored},
        {"Metric": "Vulnerabilities Open", "Value": overview.vulnerabilities_open},
        {"Metric": "Identity Issues Open", "Value": overview.identity_issues_open},
        {"Metric": "Cloud Misconfigurations Open", "Value": overview.cloud_misconfigurations_open},
        {"Metric": "Open Incidents", "Value": overview.open_incidents},
        {"Metric": "Incident Evidence Coverage %", "Value": overview.evidence_coverage_percent},
    ]
    return ReportContent(
        title="Security Posture Report",
        generated_at=datetime.now(UTC),
        sections=[ReportSection("Security Overview", rows)],
    )


async def _build_gdpr(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    now = datetime.now(UTC)

    activities = list(
        (
            await db.execute(
                select(ProcessingActivity).where(ProcessingActivity.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    dpias = list(
        (await db.execute(select(DPIA).where(DPIA.organization_id == organization_id)))
        .scalars()
        .all()
    )
    dsars = list(
        (await db.execute(select(DSAR).where(DSAR.organization_id == organization_id)))
        .scalars()
        .all()
    )
    transfers = list(
        (await db.execute(select(DataTransfer).where(DataTransfer.organization_id == organization_id)))
        .scalars()
        .all()
    )

    return ReportContent(
        title="GDPR Report",
        generated_at=now,
        sections=[
            ReportSection(
                "Processing Activities",
                [{"Activity": a.name, "Legal Basis": a.legal_basis, "Status": a.status} for a in activities],
            ),
            ReportSection(
                "DPIAs",
                [{"Title": d.title, "Risk Level": d.risk_level, "Status": d.status} for d in dpias],
            ),
            ReportSection(
                "DSARs",
                [
                    {
                        "Requester": d.requester_name,
                        "Type": d.request_type,
                        "Status": d.status,
                        "Due": d.due_at.date().isoformat(),
                        "Overdue": "Yes" if d.status != "fulfilled" and d.due_at < now else "No",
                    }
                    for d in dsars
                ],
            ),
            ReportSection(
                "International Data Transfers",
                [
                    {
                        "Recipient": t.recipient_name,
                        "Destination": t.destination_country,
                        "Mechanism": t.transfer_mechanism,
                        "Status": t.status,
                    }
                    for t in transfers
                ],
            ),
        ],
    )


async def _build_eu_ai_act(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    systems = list(
        (await db.execute(select(AISystem).where(AISystem.organization_id == organization_id)))
        .scalars()
        .all()
    )
    by_classification: dict[str, int] = {}
    for system in systems:
        by_classification[system.risk_classification] = (
            by_classification.get(system.risk_classification, 0) + 1
        )
    return ReportContent(
        title="EU AI Act Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "AI Systems by Risk Classification",
                [{"Risk Classification": k, "Count": v} for k, v in sorted(by_classification.items())],
            ),
            ReportSection(
                "AI System Detail",
                [
                    {
                        "System": s.name,
                        "Risk Classification": s.risk_classification,
                        "Status": s.status,
                        "Vendor": s.vendor or "—",
                    }
                    for s in systems
                ],
            ),
        ],
    )


async def _build_ai_inventory(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    systems = list(
        (
            await db.execute(
                select(AISystem)
                .where(AISystem.organization_id == organization_id)
                .order_by(AISystem.name)
            )
        )
        .scalars()
        .all()
    )
    rows = [
        {
            "System": s.name,
            "Vendor": s.vendor or "—",
            "Purpose": s.purpose,
            "Risk Classification": s.risk_classification,
            "Status": s.status,
        }
        for s in systems
    ]
    return ReportContent(
        title="AI Inventory",
        generated_at=datetime.now(UTC),
        sections=[ReportSection("AI Systems", rows)],
    )


async def _build_risk(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    risks = list(
        (await db.execute(select(Risk).where(Risk.organization_id == organization_id)))
        .scalars()
        .all()
    )
    by_status: dict[str, int] = {}
    for r in risks:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return ReportContent(
        title="Risk Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Risks by Status", [{"Status": k, "Count": v} for k, v in sorted(by_status.items())]
            ),
            ReportSection(
                "Risk Register",
                [
                    {
                        "Risk": r.title,
                        "Category": r.category,
                        "Likelihood": r.likelihood,
                        "Impact": r.impact,
                        "Status": r.status,
                    }
                    for r in risks
                ],
            ),
        ],
    )


async def _build_vendor(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    vendors = list(
        (await db.execute(select(Vendor).where(Vendor.organization_id == organization_id)))
        .scalars()
        .all()
    )
    vendor_names = {v.id: v.name for v in vendors}
    assessments = list(
        (
            await db.execute(
                select(VendorAssessment).where(VendorAssessment.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    return ReportContent(
        title="Vendor Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Vendors",
                [
                    {"Vendor": v.name, "Category": v.category, "Risk Tier": v.risk_tier, "Status": v.status}
                    for v in vendors
                ],
            ),
            ReportSection(
                "Vendor Assessments",
                [
                    {
                        "Vendor": vendor_names.get(a.vendor_id, "—"),
                        "Risk Conclusion": a.risk_conclusion,
                        "Assessed": a.created_at.date().isoformat(),
                    }
                    for a in assessments
                ],
            ),
        ],
    )


async def _build_sales_performance(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    intelligence = await compute_sales_intelligence(db, organization_id=organization_id)
    return ReportContent(
        title="Sales Performance",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Summary",
                [
                    {"Metric": "Win Rate %", "Value": intelligence["win_rate_percent"]},
                    {"Metric": "Average Deal Size", "Value": intelligence["average_deal_size"]},
                    {
                        "Metric": "Sequence Completion Rate %",
                        "Value": intelligence["sequence_completion_rate_percent"],
                    },
                ],
            ),
            ReportSection(
                "Pipeline Value by Stage",
                [
                    {"Stage": stage, "Value": value}
                    for stage, value in intelligence["pipeline_value_by_stage"].items()
                ],
            ),
            ReportSection(
                "Top Accounts by ICP Score",
                [
                    {
                        "Account": account.name,
                        "ICP Score": float(account.icp_score) if account.icp_score is not None else None,
                    }
                    for account in intelligence["top_accounts_by_icp_score"]
                ],
            ),
        ],
    )


async def _build_pipeline(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    intelligence = await compute_sales_intelligence(db, organization_id=organization_id)
    opportunities_result = await db.execute(
        select(Opportunity, Account.name)
        .join(Account, Account.id == Opportunity.account_id)
        .where(
            Opportunity.organization_id == organization_id,
            Opportunity.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Opportunity.stage)
    )
    return ReportContent(
        title="Pipeline Report",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Pipeline Value by Stage",
                [
                    {"Stage": stage, "Value": value}
                    for stage, value in intelligence["pipeline_value_by_stage"].items()
                ],
            ),
            ReportSection(
                "Open Opportunities",
                [
                    {
                        "Opportunity": opp.title,
                        "Account": account_name,
                        "Stage": opp.stage,
                        "Value": float(opp.value) if opp.value is not None else None,
                        "Expected Close": (
                            opp.expected_close_at.date().isoformat() if opp.expected_close_at else "—"
                        ),
                    }
                    for opp, account_name in opportunities_result.all()
                ],
            ),
        ],
    )


async def _build_support_performance(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    analytics = await compute_support_analytics(db, organization_id=organization_id)
    return ReportContent(
        title="Support Performance",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Summary",
                [
                    {"Metric": "Total Tickets", "Value": analytics["total_tickets"]},
                    {"Metric": "Open Tickets", "Value": analytics["open_tickets"]},
                    {"Metric": "Average Resolution (hours)", "Value": analytics["average_resolution_hours"]},
                    {"Metric": "Average CSAT", "Value": analytics["average_csat"]},
                    {"Metric": "CSAT Responses", "Value": analytics["csat_response_count"]},
                    {"Metric": "Average QA Score", "Value": analytics["average_qa_score"]},
                    {"Metric": "QA Scores Recorded", "Value": analytics["qa_score_count"]},
                ],
            ),
            ReportSection(
                "Tickets by Status",
                [{"Status": k, "Count": v} for k, v in analytics["tickets_by_status"].items()],
            ),
        ],
    )


async def _build_automation_roi(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    analytics = await compute_workflow_analytics(db, organization_id=organization_id)
    return ReportContent(
        title="Automation ROI",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection(
                "Summary",
                [
                    {"Metric": "Total Workflows", "Value": analytics["total_workflows"]},
                    {"Metric": "Active Workflows", "Value": analytics["active_workflows"]},
                    {"Metric": "Total Runs", "Value": analytics["total_runs"]},
                    {"Metric": "Success Rate %", "Value": analytics["success_rate_percent"]},
                    {"Metric": "Runs Awaiting Approval", "Value": analytics["awaiting_approval_count"]},
                ],
            ),
            ReportSection(
                "Runs by Status",
                [{"Status": k, "Count": v} for k, v in analytics["runs_by_status"].items()],
            ),
            ReportSection(
                "Note",
                [
                    {
                        "Note": (
                            "This build does not collect a per-workflow cost-per-manual-execution "
                            "figure, so no dollar ROI is calculated here — real run volume and "
                            "success rate above are the honest proxy for automation value delivered."
                        )
                    }
                ],
            ),
        ],
    )


async def _build_audit_evidence_pack(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    now = datetime.now(UTC)
    audits = list(
        (await db.execute(select(Audit).where(Audit.organization_id == organization_id)))
        .scalars()
        .all()
    )
    findings_result = await db.execute(
        select(AuditFinding, Audit.title)
        .join(Audit, Audit.id == AuditFinding.audit_id)
        .where(AuditFinding.organization_id == organization_id)
    )
    evidence_items = list(
        (await db.execute(select(Evidence).where(Evidence.organization_id == organization_id)))
        .scalars()
        .all()
    )
    return ReportContent(
        title="Audit Evidence Pack",
        generated_at=now,
        sections=[
            ReportSection(
                "Audits",
                [
                    {"Audit": a.title, "Auditor": a.auditor_name or "—", "Status": a.status}
                    for a in audits
                ],
            ),
            ReportSection(
                "Audit Findings",
                [
                    {"Audit": audit_title, "Finding": f.title, "Severity": f.severity, "Status": f.status}
                    for f, audit_title in findings_result.all()
                ],
            ),
            ReportSection(
                "Evidence Inventory",
                [
                    {
                        "Evidence": e.title,
                        "Valid Until": e.valid_until.date().isoformat() if e.valid_until else "No expiry set",
                        "Expired": "Yes" if e.valid_until and e.valid_until < now else "No",
                    }
                    for e in evidence_items
                ],
            ),
        ],
    )


REPORT_BUILDERS: dict[str, Callable[[AsyncSession, uuid.UUID], Awaitable[ReportContent]]] = {
    "executive_business_ai": _build_executive_business_ai,
    "board": _build_board,
    "compliance": _build_compliance,
    "security_posture": _build_security_posture,
    "gdpr": _build_gdpr,
    "eu_ai_act": _build_eu_ai_act,
    "ai_inventory": _build_ai_inventory,
    "risk": _build_risk,
    "vendor": _build_vendor,
    "sales_performance": _build_sales_performance,
    "pipeline": _build_pipeline,
    "support_performance": _build_support_performance,
    "automation_roi": _build_automation_roi,
    "audit_evidence_pack": _build_audit_evidence_pack,
}
