"""One document, addressed the same way everywhere.

An uploaded file and the indexed document made from it are two rows:
`File` is what the customer uploaded, `Document` is what the Copilot
reads. Screens hold one or the other depending on where they came from —
the library lists Files, a citation carries a Document — and the detail
page is addressed by the Document.

Rather than each surface working that out for itself, the mapping and
the naming live here. A document opened from the library and the same
document opened from a Copilot citation are then the same URL, the same
page, and the same title at the top of it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import File
from app.core.routes import document_detail_href
from app.knowledge.models import Document


def readable_title(raw: str | None) -> str:
    """`10_Special_Category_Data_Processing_Policy.docx` reads as
    "Special Category Data Processing Policy".

    The leading sort number and the extension came from somebody's
    folder, not from the document. Capitalization is left alone unless
    the whole name is lower case, in which case it gets a sentence
    capital — title-casing everything would turn "AI Governance Policy"
    into "Ai Governance Policy", and mangling an acronym the customer
    wrote correctly is worse than leaving it be.
    """
    raw = (raw or "").strip()
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", raw)
    stem = re.sub(r"^[\d\s._-]+", "", stem)
    cleaned = re.sub(r"\s{2,}", " ", stem.replace("_", " ").replace("-", " ")).strip()
    if cleaned and cleaned == cleaned.lower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return (cleaned or raw or "Untitled document")[:200]


async def documents_for_files(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
    """Map File id -> (Document id, title), in one query.

    The title travels with the id because every surface that links to a
    document also names it, and they have to agree: a library row reading
    "Gdpr overview" that opens a page headed "GDPR Compliance Overview" is
    a disagreement the reader has to stop and resolve.

    A file with no indexed document is simply absent from the result: it
    has no detail page to open yet, and the caller renders it without a
    link rather than with one that 404s.
    """
    wanted = [file_id for file_id in file_ids if file_id is not None]
    if not wanted:
        return {}

    rows = (
        await db.execute(
            select(Document.file_id, Document.id, Document.title).where(
                Document.organization_id == organization_id,
                Document.file_id.in_(wanted),
            )
        )
    ).all()
    return {file_id: (document_id, title) for file_id, document_id, title in rows}


async def document_ids_for_files(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, uuid.UUID]:
    """Just the ids, for callers that do not need the name."""
    resolved = await documents_for_files(
        db, organization_id=organization_id, file_ids=file_ids
    )
    return {file_id: document_id for file_id, (document_id, _) in resolved.items()}


async def hrefs_for_files(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Where each of these files opens, keyed by File id.

    For the surfaces that hold a File and want a link: the library, the
    evidence list, a control's evidence, a policy's current document, a
    search hit.
    """
    resolved = await documents_for_files(
        db, organization_id=organization_id, file_ids=file_ids
    )
    return {
        file_id: document_detail_href(document_id)
        for file_id, (document_id, _) in resolved.items()
    }


async def file_for_document(
    db: AsyncSession, *, organization_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[Document, File] | None:
    """The other direction: the upload behind an indexed document.

    Tenant-scoped on the Document, so a document id from another
    organization resolves to nothing rather than to somebody else's file.
    """
    document = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        return None

    file_record = (
        await db.execute(
            select(File).where(
                File.id == document.file_id,
                File.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if file_record is None:
        return None
    return (document, file_record)


__all__ = [
    "document_ids_for_files",
    "documents_for_files",
    "file_for_document",
    "hrefs_for_files",
    "readable_title",
]
