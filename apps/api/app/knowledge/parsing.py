"""Text extraction per content type (spec section 46, Document Intelligence).

Only formats with a genuine extractor are attempted. Anything else raises
UnsupportedFormatError so the caller can mark the document
`unsupported_format` rather than silently producing empty/fake content
(spec section 82, No Fake Features).
"""

from __future__ import annotations

import csv
import io

TEXT_CONTENT_TYPES = {"text/plain", "text/markdown", "text/csv"}
PDF_CONTENT_TYPES = {"application/pdf"}
DOCX_CONTENT_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
XLSX_CONTENT_TYPES = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
HTML_CONTENT_TYPES = {"text/html"}


class UnsupportedFormatError(Exception):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"No text extractor available for content type '{content_type}'")
        self.content_type = content_type


def extract_text(content_type: str, data: bytes) -> str:
    if content_type in TEXT_CONTENT_TYPES:
        return _extract_text_plain(content_type, data)
    if content_type in PDF_CONTENT_TYPES:
        return _extract_pdf(data)
    if content_type in DOCX_CONTENT_TYPES:
        return _extract_docx(data)
    if content_type in XLSX_CONTENT_TYPES:
        return _extract_xlsx(data)
    if content_type in HTML_CONTENT_TYPES:
        return _extract_html(data)
    raise UnsupportedFormatError(content_type)


def _extract_text_plain(content_type: str, data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if content_type == "text/csv":
        # Normalize CSV into readable row text rather than raw comma soup,
        # so chunking/embedding operates on something coherent.
        reader = csv.reader(io.StringIO(text))
        return "\n".join(", ".join(row) for row in reader)
    return text


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines: list[str] = []
    for sheet in workbook.worksheets:
        lines.append(f"# {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell) for cell in row if cell is not None]
            if cells:
                lines.append(", ".join(cells))
    return "\n".join(lines)


def _extract_html(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return str(soup.get_text(separator="\n", strip=True))
