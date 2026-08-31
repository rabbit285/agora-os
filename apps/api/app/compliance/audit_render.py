"""The audit report as a document somebody reads end to end.

Takes an `AuditReportPreview` and nothing else, so what is generated is
by construction what was previewed. Every number, every conclusion and
every date on the page came out of the preview the person confirmed.

The order is how an audit report is actually read, not how the data is
stored:

    1. Audit information       — what this is, on the first page
    2. Executive summary       — the result, in sentences
    3. Scope and methodology   — what was covered and how
    4. Audit results summary   — the counts, with their zeros
    5. Findings                — grouped worst-first
    6. Remediation and verification
    7. Evidence index
    8. Known limitations
    9. Auditor sign-off
    Appendix A                 — requirement by requirement

Page one has to work on its own: a compliance manager who reads nothing
else should still know the result. Everything after it is the support,
and the requirement-by-requirement table is an appendix because a 100-
requirement audit would otherwise bury the findings behind fifty rows of
"No finding".

Two things recur and are always labelled: **audit conclusion at
completion**, which is a person's and cannot move, and **current
remediation status as of report generation**, which moves constantly.
Neither is ever printed without saying which it is.

The visual register is deliberately plain. One accent, used for rules
and headings; two severity inks, used only on severity words. An audit
report banded in colour reads as marketing, and the reader stops
distinguishing the one finding that matters.
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.compliance.audit_report import AuditReportPreview, FindingLine

_ACCENT = colors.HexColor("#0F5C4A")
_INK = colors.HexColor("#1A1A1A")
_MUTED = colors.HexColor("#5A5A5A")
_RULE = colors.HexColor("#DDDDDD")
_BAND = colors.HexColor("#F4F6F5")

# Colour only on the severity word itself, and only two steps of it.
_SEVERITY_INK = {
    "critical": colors.HexColor("#8C1D18"),
    "high": colors.HexColor("#8C1D18"),
    "medium": colors.HexColor("#7A4B00"),
    "low": _MUTED,
}

_DATE_FORMAT = "%B %d, %Y"

# Left column of every label/value block. Fixed so the eye tracks one
# edge down the whole document instead of a new one per section.
_LABEL_WIDTH = 42 * mm

# How much vertical room a finding block needs before it is worth
# starting one. Below this the heading would sit alone at the foot of a
# page with its conclusion overleaf, which is the specific thing §23
# forbids.
_FINDING_MIN = 46 * mm


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AuditTitle",
            parent=base["Title"],
            fontSize=21,
            leading=26,
            textColor=_INK,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "AuditSubtitle",
            parent=base["Normal"],
            fontSize=11.5,
            leading=15,
            textColor=_MUTED,
        ),
        "h2": ParagraphStyle(
            "AuditH2",
            parent=base["Heading2"],
            fontSize=12,
            leading=15,
            textColor=_ACCENT,
            fontName="Helvetica-Bold",
            spaceBefore=18,
            spaceAfter=7,
        ),
        "h3": ParagraphStyle(
            "AuditH3",
            parent=base["Normal"],
            fontSize=10.5,
            leading=14,
            textColor=_INK,
            fontName="Helvetica-Bold",
            spaceBefore=12,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "AuditBody",
            parent=base["Normal"],
            fontSize=10,
            leading=14.5,
            textColor=_INK,
            spaceAfter=4,
        ),
        "lead": ParagraphStyle(
            "AuditLead",
            parent=base["Normal"],
            fontSize=10.5,
            leading=16,
            textColor=_INK,
            spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "AuditSmall",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=_MUTED,
        ),
        "label": ParagraphStyle(
            "AuditLabel",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12.5,
            textColor=_MUTED,
        ),
        "value": ParagraphStyle(
            "AuditValue",
            parent=base["Normal"],
            fontSize=10,
            leading=13.5,
            textColor=_INK,
        ),
        "cell": ParagraphStyle(
            "AuditCell",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11.5,
            textColor=_INK,
        ),
        "cellmuted": ParagraphStyle(
            "AuditCellMuted",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11.5,
            textColor=_MUTED,
        ),
        "head": ParagraphStyle(
            "AuditHead",
            parent=base["Normal"],
            fontSize=8,
            leading=10.5,
            textColor=_ACCENT,
            fontName="Helvetica-Bold",
        ),
    }


def _escape(text: str | None) -> str:
    """Reportlab's mini-markup would otherwise swallow a control title
    containing angle brackets, or raise on a stray ampersand."""
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _date(value: datetime | None) -> str:
    return value.strftime(_DATE_FORMAT) if value else "—"


def _short_date(value: datetime | None) -> str:
    return value.strftime("%b %d, %Y") if value else "—"


def _facts(rows: list[tuple[str, str]], styles) -> Table:
    """A label/value block. The workhorse of the whole document."""
    data = [
        [Paragraph(_escape(label), styles["label"]), Paragraph(_escape(value), styles["value"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[_LABEL_WIDTH, None], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _metrics_table(rows: list[tuple[str, str, bool]], styles) -> Table:
    """The counts, right-aligned so the numbers line up as a column."""
    data = [
        [
            Paragraph(
                f"<b>{_escape(label)}</b>" if strong else _escape(label),
                styles["value" if strong else "cell"],
            ),
            Paragraph(
                f"<b>{_escape(value)}</b>" if strong else _escape(value),
                styles["value" if strong else "cell"],
            ),
        ]
        for label, value, strong in rows
    ]
    table = Table(data, colWidths=[None, 26 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, _RULE),
            ]
        )
    )
    return table


def _grid(header: list[str], rows: list[list], widths: list, styles) -> Table:
    """A table whose header repeats on every page it spans.

    The header cells are Paragraphs rather than bare strings so long
    column names wrap instead of colliding — which is how "Auditor
    conclusion" and "Now" ended up printed as "Auditor conclusionNow".
    """
    data = [[Paragraph(_escape(name), styles["head"]) for name in header]] + rows
    table = Table(data, repeatRows=1, hAlign="LEFT", colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), _BAND),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, _ACCENT),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, _RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _auditor_rows(auditor) -> list[tuple[str, str]]:
    """The auditor as fields, not as a name with a suffix.

    "Zach Warren (external)" was two claims glued into one string, and
    the second was inferred rather than known. Type is its own row, the
    firm is its own row, and an auditor nobody has classified is reported
    as unresolved rather than assigned a side.
    """
    rows: list[tuple[str, str]] = [("Auditor", auditor.name or "Not recorded")]
    if auditor.type_label:
        rows.append(("Auditor type", auditor.type_label))
    if auditor.organization:
        rows.append(("Auditor organization", auditor.organization))
    elif auditor.unresolved:
        rows.append(
            (
                "Auditor type",
                "Not recorded for this audit",
            )
        )
    return rows


def _subtitle(preview: AuditReportPreview) -> str:
    """What the report is, under the title.

    Most audits are named after their framework already — "ISO 42001 -
    Agora Origin" — and prefixing the framework again gives "ISO 42001 —
    ISO 42001 - Agora Origin", which reads like a bug because it is one.
    """
    title = preview.audit_title
    framework = preview.framework_name
    if framework and framework.lower() not in title.lower():
        return f"{framework} — {title}"
    return title


def _section(title: str, styles, story: list) -> None:
    """A heading that will not be left alone at the foot of a page."""
    story.append(CondPageBreak(28 * mm))
    story.append(Paragraph(_escape(title), styles["h2"]))
    story.append(HRFlowable(width="100%", thickness=0.6, color=_RULE, spaceAfter=8))


def _footer(preview: AuditReportPreview):
    """Every page says what it is, whose it is, and where it sits.

    A page of an audit report that reaches somebody's desk on its own
    should still identify the audit and its classification.
    """
    left = " · ".join(
        part
        for part in (
            "Veyntra Internal Audit Report",
            preview.audit_title,
            f"Report v{preview.next_version}",
        )
        if part
    )

    def draw(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(_MUTED)
        width, _ = A4
        y = 12 * mm
        canvas.setStrokeColor(_RULE)
        canvas.setLineWidth(0.4)
        canvas.line(20 * mm, y + 5 * mm, width - 20 * mm, y + 5 * mm)
        canvas.drawString(20 * mm, y, left[:110])
        canvas.drawRightString(
            width - 20 * mm,
            y,
            f"{preview.classification} · Page {document.page}",
        )
        canvas.restoreState()

    return draw


def _finding_block(line: FindingLine, styles) -> list:
    """One finding, with the requirement as its subject.

    Order matters: the requirement, then what the auditor concluded, then
    what Veyntra could establish, then where remediation stands. The
    conclusion sits above the assessment because the conclusion is the
    audit result and the assessment is the support for it.
    """
    heading = " — ".join(
        part for part in (line.reference_code, line.requirement_title) if part
    ) or line.title

    block: list = [
        Paragraph(_escape(heading), styles["h3"]),
    ]

    rows: list[tuple[str, str]] = [
        ("Auditor conclusion", line.conclusion_label),
    ]
    if line.control_title:
        rows.append(("Control", line.control_title))
    if line.evidence_state_label:
        rows.append(("Evidence state at audit", line.evidence_state_label))
    rows.append(("Current remediation", line.current_status_label))
    if line.remediation_owner:
        rows.append(("Owner", line.remediation_owner))
    if line.remediation_due:
        rows.append(("Due", _date(line.remediation_due)))
    if line.verified_at:
        rows.append(
            (
                "Verified",
                _date(line.verified_at)
                + (f" by {line.verified_by}" if line.verified_by else ""),
            )
        )
    block.append(_facts(rows, styles))

    if line.assessment:
        block.append(Spacer(1, 2))
        block.append(
            _facts([("Veyntra assessment", line.assessment)], styles)
        )
    if line.not_evidenced:
        block.append(_facts([("Not evidenced", line.not_evidenced)], styles))
    if line.auditor_note:
        block.append(_facts([("Auditor note", line.auditor_note)], styles))
    elif line.rationale_gap:
        # §6: the conclusion and the evidence state disagree and nobody
        # wrote down why. Saying so is the only honest option — the
        # alternative is a report that looks like it contradicts itself,
        # or an invented rationale.
        block.append(
            _facts(
                [
                    (
                        "Auditor note",
                        "No rationale was recorded for this conclusion.",
                    )
                ],
                styles,
            )
        )

    block.append(Spacer(1, 8))
    return block


def render_audit_report_pdf(preview: AuditReportPreview) -> bytes:
    """The report, from the preview and nothing else."""
    styles = _styles()
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=24 * mm,
        title=preview.title,
        author="Veyntra",
        subject=f"Internal audit report — {preview.audit_title}",
    )
    content = pdf.width

    story: list = [
        Paragraph("Internal Audit Report", styles["title"]),
        Paragraph(_escape(_subtitle(preview)), styles["subtitle"]),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1.2, color=_ACCENT, spaceAfter=4),
    ]

    # --- 1. audit information --------------------------------------------
    _section("1. Audit information", styles, story)
    facts: list[tuple[str, str]] = []
    if preview.organization_name:
        facts.append(("Organization", preview.organization_name))
    if not preview.organization_name_configured:
        facts.append(
            (
                "",
                "Set the organization name in Organization Settings so it "
                "appears on future reports.",
            )
        )
    facts.append(
        ("Framework", preview.framework_name or "Custom scope (no framework)")
    )
    if preview.framework_basis:
        facts.append(("Requirement set", preview.framework_basis))
    facts += _auditor_rows(preview.auditor)
    facts += [
        ("Audit status", preview.status_label),
        ("Started", _date(preview.started_at)),
        ("Completed", _date(preview.completed_at)),
        ("Report version", str(preview.next_version)),
        ("Report generated", _date(preview.generated_for)),
        ("Classification", preview.classification),
    ]
    story.append(_facts(facts, styles))

    # --- 2. executive summary --------------------------------------------
    _section("2. Executive summary", styles, story)
    for sentence in preview.executive_summary:
        story.append(Paragraph(_escape(sentence), styles["lead"]))

    story.append(Spacer(1, 4))
    story.append(
        _metrics_table(
            [
                (metric.label, metric.value, metric.emphasis)
                for metric in preview.metrics
            ],
            styles,
        )
    )

    # --- 3. scope and methodology ----------------------------------------
    _section("3. Scope and methodology", styles, story)
    story.append(Paragraph("Scope", styles["h3"]))
    story.append(
        Paragraph(
            _escape(preview.scope or "No scope statement was recorded."),
            styles["body"],
        )
    )
    story.append(Paragraph("Methodology", styles["h3"]))
    for paragraph in preview.methodology:
        story.append(Paragraph(_escape(paragraph), styles["body"]))

    # --- 4. audit results summary ----------------------------------------
    _section("4. Audit results summary", styles, story)
    story.append(
        Paragraph(
            "Audit conclusions are as recorded by the auditor at completion "
            "and do not change. Remediation status is as at the generation "
            "date of this report.",
            styles["small"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("Auditor conclusions", styles["h3"]))
    story.append(
        _metrics_table(
            [(m.label, m.value, False) for m in preview.conclusion_summary], styles
        )
    )
    story.append(Paragraph("Remediation status", styles["h3"]))
    story.append(
        _metrics_table(
            [(g.label, str(g.count), False) for g in preview.remediation], styles
        )
    )

    # --- 5. findings ------------------------------------------------------
    _section("5. Findings", styles, story)
    if not preview.findings:
        story.append(
            Paragraph("No audit findings were recorded.", styles["body"])
        )
    else:
        for group in preview.findings_by_severity:
            story.append(CondPageBreak(34 * mm))
            story.append(
                Paragraph(
                    f"{_escape(group.label)} ({group.count})",
                    ParagraphStyle(
                        f"sev_{group.key}",
                        parent=styles["h3"],
                        fontSize=11,
                        textColor=_SEVERITY_INK.get(group.severity, _INK),
                        spaceBefore=14,
                    ),
                )
            )
            for line in group.findings:
                # §23: a finding heading never ends a page with its
                # conclusion overleaf.
                story.append(CondPageBreak(_FINDING_MIN))
                story.append(KeepTogether(_finding_block(line, styles)))

    if preview.superseded_findings:
        story.append(Paragraph("Replaced conclusions", styles["h3"]))
        story.append(
            Paragraph(
                "The auditor revised these conclusions during the audit. They "
                "are retained for traceability and are not counted as "
                "findings.",
                styles["small"],
            )
        )
        story.append(Spacer(1, 5))
        story.append(
            _grid(
                ["Ref", "Original conclusion", "Replaced", "Reason"],
                [
                    [
                        Paragraph(_escape(line.reference_code or "—"), styles["cell"]),
                        Paragraph(
                            _escape(f"{line.conclusion_label}: {line.title}"),
                            styles["cell"],
                        ),
                        Paragraph(_short_date(line.superseded_at), styles["cell"]),
                        Paragraph(
                            _escape(line.superseded_reason or "—"), styles["cellmuted"]
                        ),
                    ]
                    for line in preview.superseded_findings
                ],
                [16 * mm, content - 16 * mm - 24 * mm - 48 * mm, 24 * mm, 48 * mm],
                styles,
            )
        )

    # --- 6. remediation and verification ----------------------------------
    _section("6. Remediation and verification", styles, story)
    story.append(
        Paragraph(
            "Current remediation status as of report generation. Remediation "
            "continues after an audit closes; later progress does not change "
            "the audit conclusions recorded above.",
            styles["small"],
        )
    )
    story.append(Spacer(1, 6))
    if not preview.remediation_rows:
        story.append(
            Paragraph(
                "No remediation items were opened by this audit.", styles["body"]
            )
        )
    else:
        story.append(
            _grid(
                ["Ref", "Finding", "Conclusion", "Owner", "Status", "Due"],
                [
                    [
                        Paragraph(_escape(line.reference_code or "—"), styles["cell"]),
                        Paragraph(
                            _escape(line.requirement_title or line.title),
                            styles["cell"],
                        ),
                        Paragraph(_escape(line.conclusion_label), styles["cell"]),
                        Paragraph(
                            _escape(line.remediation_owner or "Unassigned"),
                            styles["cellmuted"],
                        ),
                        Paragraph(_escape(line.current_status_label), styles["cell"]),
                        Paragraph(
                            _short_date(line.remediation_due), styles["cellmuted"]
                        ),
                    ]
                    for line in preview.remediation_rows
                ],
                [
                    15 * mm,
                    content - 15 * mm - 26 * mm - 24 * mm - 26 * mm - 22 * mm,
                    26 * mm,
                    24 * mm,
                    26 * mm,
                    22 * mm,
                ],
                styles,
            )
        )

    story.append(Paragraph("Verification history", styles["h3"]))
    if preview.verification:
        story.append(
            _grid(
                ["Verified", "Ref", "Finding", "Verified by", "What was checked"],
                [
                    [
                        Paragraph(_short_date(line.verified_at), styles["cell"]),
                        Paragraph(_escape(line.reference_code or "—"), styles["cell"]),
                        Paragraph(
                            _escape(line.requirement_title or line.title),
                            styles["cell"],
                        ),
                        Paragraph(_escape(line.verified_by or "—"), styles["cell"]),
                        Paragraph(
                            _escape(line.verification_note or "—"), styles["cellmuted"]
                        ),
                    ]
                    for line in preview.verification
                ],
                [
                    22 * mm,
                    14 * mm,
                    content - 22 * mm - 14 * mm - 26 * mm - 52 * mm,
                    26 * mm,
                    52 * mm,
                ],
                styles,
            )
        )
    else:
        story.append(
            Paragraph(
                "No findings had been verified and closed as of the report "
                "generation date.",
                styles["body"],
            )
        )

    # --- 7. evidence index ------------------------------------------------
    _section("7. Evidence index", styles, story)
    if preview.evidence_index:
        story.append(
            Paragraph(
                "Document versions are as reviewed at the audit preparation "
                "date. Documents may have been revised since.",
                styles["small"],
            )
        )
        story.append(Spacer(1, 6))
        story.append(
            _grid(
                ["Document", "Version reviewed", "Evidence state at audit", "Reviewed against"],
                [
                    [
                        Paragraph(_escape(line.title), styles["cell"]),
                        Paragraph(_escape(line.version_label), styles["cell"]),
                        Paragraph(
                            _escape(", ".join(line.evidence_states) or "—"),
                            styles["cellmuted"],
                        ),
                        Paragraph(
                            _escape(", ".join(line.requirement_codes)),
                            styles["cellmuted"],
                        ),
                    ]
                    for line in preview.evidence_index
                ],
                [
                    content - 28 * mm - 34 * mm - 42 * mm,
                    28 * mm,
                    34 * mm,
                    42 * mm,
                ],
                styles,
            )
        )
    else:
        story.append(
            Paragraph(
                "No evidence was on file for the requirements in scope.",
                styles["body"],
            )
        )

    # --- 8. known limitations ---------------------------------------------
    _section("8. Known limitations", styles, story)
    for limitation in preview.limitations:
        story.append(Paragraph(f"• {_escape(limitation)}", styles["body"]))

    # --- 9. auditor sign-off ----------------------------------------------
    _section("9. Auditor sign-off", styles, story)
    sign_off = preview.sign_off
    rows = _auditor_rows(sign_off.auditor)
    rows += [
        ("Audit completed", _date(sign_off.completed_at)),
        ("Report generated", _date(sign_off.generated_at)),
    ]
    # §7: the person who pressed generate is a different role from the
    # auditor. Both are named, so a report issued by a colleague still
    # says who conducted the audit.
    if sign_off.generated_by:
        rows.append(("Generated by", sign_off.generated_by))
    rows.append(("Report version", str(sign_off.report_version)))
    if sign_off.approved_by:
        rows.append(("Approved by", sign_off.approved_by))
        rows.append(("Approved at", _date(sign_off.approved_at)))
    story.append(_facts(rows, styles))
    if not sign_off.approved_by:
        # No formal approval is recorded against an audit in this
        # product. Drawing a signature block nobody signed would be a
        # forgery in a document people rely on.
        story.append(Spacer(1, 2))
        story.append(
            Paragraph(
                "No formal sign-off approval is recorded in Veyntra for this "
                "audit. The identities and timestamps above are the record.",
                styles["small"],
            )
        )

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.6, color=_RULE, spaceAfter=8))
    story.append(Paragraph(_escape(preview.disclaimer), styles["small"]))

    # --- appendix A --------------------------------------------------------
    story.append(PageBreak())
    story.append(
        Paragraph("Appendix A — Requirement-by-requirement results", styles["h2"])
    )
    story.append(HRFlowable(width="100%", thickness=0.6, color=_RULE, spaceAfter=8))
    story.append(
        Paragraph(
            "Evidence state is what Veyntra assessed from the record at audit "
            "preparation. The auditor conclusion is the formal audit result. "
            "Current remediation status is as at the generation date of this "
            "report.",
            styles["small"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        _grid(
            [
                "Ref",
                "Requirement",
                "Evidence state at audit",
                "Auditor conclusion",
                "Current remediation status",
            ],
            [
                [
                    Paragraph(_escape(line.reference_code), styles["cell"]),
                    Paragraph(_escape(line.requirement_title), styles["cell"]),
                    Paragraph(
                        _escape(line.evidence_state_label or "—"), styles["cellmuted"]
                    ),
                    Paragraph(_escape(line.decision_label), styles["cell"]),
                    Paragraph(
                        _escape(line.current_remediation_label or "—"),
                        styles["cellmuted"],
                    ),
                ]
                for line in preview.conclusions
            ],
            [
                15 * mm,
                content - 15 * mm - 30 * mm - 26 * mm - 30 * mm,
                30 * mm,
                26 * mm,
                30 * mm,
            ],
            styles,
        )
    )

    draw = _footer(preview)
    pdf.build(story, onFirstPage=draw, onLaterPages=draw)
    return buffer.getvalue()


__all__ = ["render_audit_report_pdf"]
