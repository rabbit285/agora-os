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
