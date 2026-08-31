"""Turning an approved review into the file a customer receives.

Three outputs, three shapes:

- **Security Review Summary** — a PDF somebody in a procurement team
  reads. Prose, not a grid: an approved answer is two or three sentences
  that often carry a qualification, and a table cell truncates exactly
  the part that matters. `app.reporting.rendering.render_pdf` is
  deliberately not reused for this; it renders any report as
  heading-plus-table, which is right for the analytics it was built for
  and wrong for a document going outside the organization.
- **Completed questionnaire** — an XLSX. Where the customer sent their
  own spreadsheet we answer in their columns; otherwise a clean sheet in
  ours.
- **Assurance pack** — a ZIP of the above plus the documents somebody
  cleared for sharing, with an evidence index naming what each one
  supports.

The design brief is restraint. This is an assurance document, not a
brochure: one accent rule, one typeface, generous whitespace, and no
claim the underlying record does not support. Every renderer here takes
an `ExportPreview` and nothing else, so what is generated is by
construction what was previewed.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.compliance.review_export import SECTION_LABELS, ExportPreview

# One accent, used for rules and headings only. A customer-facing
# compliance document that looks designed looks like marketing, and the
# reader is trying to decide whether to trust the organization.
_ACCENT = colors.HexColor("#0F5C4A")
_INK = colors.HexColor("#1A1A1A")
_MUTED = colors.HexColor("#5A5A5A")

_DATE_FORMAT = "%B %d, %Y"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReviewTitle",
            parent=base["Title"],
            fontSize=22,
            leading=27,
            textColor=_INK,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "ReviewSubtitle",
            parent=base["Normal"],
            fontSize=11,
            leading=15,
            textColor=_MUTED,
        ),
        "h2": ParagraphStyle(
            "ReviewH2",
            parent=base["Heading2"],
            fontSize=13,
            leading=17,
            textColor=_ACCENT,
            spaceBefore=16,
            spaceAfter=6,
        ),
        "question": ParagraphStyle(
            "ReviewQuestion",
            parent=base["Normal"],
            fontSize=10.5,
            leading=14,
            textColor=_INK,
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "ReviewBody",
            parent=base["Normal"],
            fontSize=10,
            leading=14.5,
            textColor=_INK,
        ),
        "small": ParagraphStyle(
            "ReviewSmall",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=_MUTED,
        ),
    }


def _escape(text: str | None) -> str:
    """Reportlab's mini-markup means angle brackets and ampersands in an
    approved answer would otherwise be swallowed or raise."""
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_summary_pdf(preview: ExportPreview) -> bytes:
    """The Security Review Summary, as the customer reads it."""
    styles = _styles()
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=preview.title,
        author="Veyntra",
    )

    story: list[object] = [
        Paragraph(_escape(preview.title), styles["title"]),
        Paragraph(
            _escape(
                " · ".join(
                    part
                    for part in (
                        preview.customer_name,
                        preview.review_title,
                    )
                    if part
                )
            ),
            styles["subtitle"],
        ),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1.2, color=_ACCENT, spaceAfter=14),
    ]

    facts = [
        ("Customer", preview.customer_name or "Not recorded"),
        ("Review", preview.review_title),
        ("Status", preview.review_status_label),
        ("Review date", preview.review_date.strftime(_DATE_FORMAT)),
    ]
    if preview.review_archived:
        # §26: the reader should know this is history, not a live
        # position, before they act on it.
        facts.append(("Note", "Generated from an archived review"))
    story.append(_fact_table(facts, styles))

    if preview.introduction:
        story.append(Paragraph("Introduction", styles["h2"]))
        story.append(Paragraph(_escape(preview.introduction), styles["body"]))

    if "executive_summary" in preview.sections:
        story.append(Paragraph(SECTION_LABELS["executive_summary"], styles["h2"]))
        story.append(Paragraph(_escape(_executive_summary(preview)), styles["body"]))

    if "completion" in preview.sections:
        progress = preview.progress
        story.append(Paragraph(SECTION_LABELS["completion"], styles["h2"]))
        story.append(
            _fact_table(
                [
                    ("Questionnaires", str(progress.questionnaires)),
                    ("Questions", str(progress.total)),
                    ("Approved", str(progress.approved)),
                    (
                        "Outstanding",
                        str(progress.total - progress.approved),
                    ),
                    ("Complete", f"{progress.percent_complete}%"),
                ],
                styles,
            )
        )

    if "responses" in preview.sections and preview.answers:
        story.append(Paragraph(SECTION_LABELS["responses"], styles["h2"]))
        for line in preview.answers:
            block: list[object] = [
                Paragraph(_escape(line.question), styles["question"]),
                Paragraph(_escape(line.answer), styles["body"]),
            ]
            if "evidence" in preview.sections and line.sources:
                block.append(
                    Paragraph(
                        "Supporting sources: " + _escape(", ".join(line.sources)),
                        styles["small"],
                    )
                )
            # Kept together so a question never sits alone at the foot of
            # a page with its answer overleaf.
            story.append(KeepTogether(block))

    if "disclosures" in preview.sections and preview.disclosures:
        story.append(Paragraph(SECTION_LABELS["disclosures"], styles["h2"]))
        story.append(
            Paragraph(
                "The following approved responses record a limitation. They "
                "are reproduced here in full.",
                styles["small"],
            )
        )
        for disclosure in preview.disclosures:
            story.append(Spacer(1, 4))
            story.append(Paragraph("— " + _escape(disclosure), styles["body"]))

    included = preview.included_documents
    if "evidence" in preview.sections and included:
        story.append(Paragraph(SECTION_LABELS["evidence"], styles["h2"]))
        rows = [["Document", "Type", "Version", "Status"]]
        for document in included:
            rows.append(
                [
                    document.title,
                    document.kind,
                    document.version or "—",
                    (document.status or "—").replace("_", " ").capitalize(),
                ]
            )
        story.append(_grid(rows))

    if "reviewer" in preview.sections:
        story.append(Paragraph(SECTION_LABELS["reviewer"], styles["h2"]))
        approved = sum(1 for line in preview.answers if line.approved_at)
        story.append(
            Paragraph(
                _escape(
                    f"{approved} response{'' if approved == 1 else 's'} in this "
                    f"report {'was' if approved == 1 else 'were'} reviewed and "
                    "approved by the organization before release. Approval "
                    "records are retained in Veyntra."
                ),
                styles["body"],
            )
        )

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.6, color=_MUTED, spaceAfter=8))
    story.append(Paragraph(_escape(preview.disclaimer), styles["small"]))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"Generated from Veyntra on "
            f"{preview.review_date.strftime('%B %d, %Y at %H:%M UTC')}.",
            styles["small"],
        )
    )

    pdf.build(story)
    return buffer.getvalue()


def _executive_summary(preview: ExportPreview) -> str:
    """Assembled from the counts, not written about them.

    Every clause here is a restatement of a number on the record. The
    sentence a model would write instead is the one that ends up
    claiming compliance the evidence does not support.
    """
    progress = preview.progress
    customer = preview.customer_name or "the customer"
    parts = [
        f"This report summarizes the security review conducted for {customer}.",
        f"It covers {progress.questionnaires} questionnaire"
        f"{'' if progress.questionnaires == 1 else 's'} containing "
        f"{progress.total} question{'' if progress.total == 1 else 's'}, of which "
        f"{progress.approved} "
        f"{'has' if progress.approved == 1 else 'have'} an approved response.",
    ]
    if preview.disclosures:
        count = len(preview.disclosures)
        parts.append(
            f"{count} response{'' if count == 1 else 's'} record"
            f"{'s' if count == 1 else ''} a limitation; "
            f"{'it is' if count == 1 else 'these are'} set out under "
            "Known disclosures and limitations."
        )
    included = preview.included_documents
    if included:
        parts.append(
            f"{len(included)} supporting document"
            f"{'' if len(included) == 1 else 's'} "
            f"{'is' if len(included) == 1 else 'are'} referenced."
        )
    return " ".join(parts)


def _fact_table(rows: list[tuple[str, str]], styles) -> Table:
    data = [
        [Paragraph(label, styles["small"]), Paragraph(_escape(value), styles["body"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[34 * mm, None], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _grid(rows: list[list[str]]) -> Table:
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, 0), _ACCENT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, _ACCENT),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#DDDDDD")),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def render_questionnaire_xlsx(preview: ExportPreview) -> bytes:
    """The completed questionnaire.

    Where the customer sent their own spreadsheet, their column headings
    are used and their question order preserved — a security team that
    sent 42 rows wants those 42 rows back, not a different document
    containing the same answers. Where they did not, a clean sheet in our
    own headings, which is the honest alternative rather than a guess at
    a layout nobody supplied.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Questionnaire"

    mapping = preview.column_mapping or {}
    headers = [
        mapping.get("question") or "Question",
        mapping.get("answer") or "Answer",
        mapping.get("category") or "Category",
        "Supporting sources",
    ]
    sheet.append(headers)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", start_color="0F5C4A")
    for column in range(1, len(headers) + 1):
        cell = sheet.cell(row=1, column=column)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for line in preview.answers:
        sheet.append(
            [
                line.question,
                line.answer,
                line.category or "",
                ", ".join(line.sources),
            ]
        )

    widths = [58, 76, 18, 40]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "A2"

    # A second sheet with the provenance, so the customer can see what
    # this file is without it cluttering the answers.
    about = workbook.create_sheet("About")
    for label, value in (
        ("Customer", preview.customer_name or "Not recorded"),
        ("Review", preview.review_title),
        ("Status", preview.review_status_label),
        ("Generated", preview.review_date.strftime("%B %d, %Y %H:%M UTC")),
        ("Source file", preview.source_filename or "Not supplied"),
        ("Disclaimer", preview.disclaimer),
    ):
        about.append([label, value])
    about.column_dimensions["A"].width = 18
    about.column_dimensions["B"].width = 90
    for row in about.iter_rows():
        row[0].font = Font(bold=True)
        row[1].alignment = Alignment(wrap_text=True, vertical="top")

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def render_evidence_index(preview: ExportPreview) -> str:
    """A plain-text index naming each document and what it supports.

    Deliberately readable without opening anything: somebody receiving a
    ZIP should be able to see what is in it from one file. No chunk
    identifiers, no internal ids — the customer gets document names.
    """
    lines = [
        "EVIDENCE INDEX",
        "",
        f"Customer: {preview.customer_name or 'Not recorded'}",
        f"Review:   {preview.review_title}",
        f"Prepared: {preview.review_date.strftime('%B %d, %Y')}",
        "",
    ]
    included = preview.included_documents
    if not included:
        lines.append("No supporting documents were included in this package.")
    for number, document in enumerate(included, start=1):
        lines.append(f"{number}. {document.title}")
        lines.append(f"   Type:    {document.kind}")
        if document.version:
            lines.append(f"   Version: {document.version}")
        if document.status:
            lines.append(
                f"   Status:  {document.status.replace('_', ' ').capitalize()}"
            )
        if document.supports:
            lines.append(f"   Supports: {', '.join(document.supports)}")
        lines.append("")

    lines.append("")
    lines.append(preview.disclaimer)
    return "\n".join(lines)


def render_evidence_pack(
    preview: ExportPreview,
    *,
    summary_pdf: bytes | None = None,
    questionnaire_xlsx: bytes | None = None,
    documents: list[tuple[str, bytes]] | None = None,
) -> bytes:
    """The assurance pack: exactly what the preview listed, and nothing else.

    `documents` carries the file bytes the caller fetched for the
    included documents. It is passed in rather than read here so this
    stays a pure function of the preview — what goes in the ZIP is what
    was on the screen.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("EVIDENCE_INDEX.txt", render_evidence_index(preview))
        if summary_pdf:
            archive.writestr("Security Review Summary.pdf", summary_pdf)
        if questionnaire_xlsx:
            archive.writestr("Completed Questionnaire.xlsx", questionnaire_xlsx)
        for filename, payload in documents or []:
            archive.writestr(f"documents/{filename}", payload)
    return buffer.getvalue()


__all__ = [
    "render_evidence_index",
    "render_evidence_pack",
    "render_questionnaire_xlsx",
    "render_summary_pdf",
]
