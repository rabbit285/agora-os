"""Working out what a document is.

Separate from working out what it evidences, and that separation is the
whole point of this module.

The two used to be one model call, on the reasoning that classification
and mapping are one reading of one document — true, and it held right up
until a customer's first upload. A brand-new organization has no
controls, so the mapping half had nothing to answer; the combined call
returned early, and the classification went with it. The document came
back unclassified, which meant no Managed Policy, which meant the first
thing a new customer did in the product produced a row with a filename
and nothing else.

"What is this document?" and "which of your controls does it evidence?"
are different questions. The first has an answer on day one. The second
does not have an answer until there are controls, and a product that
refuses to answer the first because it cannot answer the second has the
dependency backwards.

Cost: for an organization that *does* have controls this is a second
call. It reads the opening of the document rather than all of it, so it
is a small fraction of the mapping call — and the mapping prompt still
asks the model what the document is, because knowing that makes it map
better. What changed is that the answer here is the one that gets kept.
"""

from __future__ import annotations

import logging
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import GenerateRequest, ModelGateway
from app.core.models import File

logger = logging.getLogger("agora.compliance.classification")

# How much of the document the classifier reads. A document says what it
# is in its title, its first heading and its purpose statement; feeding
# it forty pages to learn "Privacy Notice" is paying for tokens that
# change nothing.
CLASSIFY_HEAD_CHARS = 4000


class DocumentClassification(BaseModel):
    """What a document is, in the words the document itself uses."""

    document_type: str = Field(
        description=(
            "What this document is, in two or three words, using the term the "
            "document itself uses. Examples: 'AI Governance Policy', 'Privacy "
            "Notice', 'Record of Processing Activities', 'Data Processing "
            "Agreement', 'Vendor Security Assessment', 'Incident Response "
            "Procedure', 'Audit Report'. If it is genuinely unclear, say "
            "'Unclassified' rather than guessing."
        )
    )
    document_domain: str = Field(
        description=(
            "The compliance domain it belongs to, e.g. 'Privacy / GDPR', "
            "'Security', 'AI Governance', 'Vendor Management'. Use 'General' "
            "when it does not clearly belong to one."
        )
    )


def build_prompt(document_text: str) -> str:
    """Ask what the document is, and nothing else.

    No controls, no frameworks, no evidence. Mentioning them here is what
    made this answer depend on an organization's setup in the first
    place.
    """
    head = (document_text or "")[:CLASSIFY_HEAD_CHARS]
    return (
        "Read the beginning of this document and say what kind of document it is.\n\n"
        "Answer from what the document says about itself — its title, its "
        "headings, its purpose statement. Do not guess from what it might be "
        "used for, and do not infer a type the document does not support.\n\n"
        "If the text is too fragmentary to tell, answer 'Unclassified'. That is "
        "a better answer than a confident wrong one.\n\n"
        "--- document ---\n"
        f"{head}\n"
        "--- end ---"
    )


# Answers that mean "I could not tell". Stored as absent rather than as
# text, so a later backfill tries again instead of treating a shrug as a
# settled classification — and so nothing downstream has to know that
# "Unclassified" is not a kind of document.
_NON_ANSWERS = frozenset({"unclassified", "unknown", "n/a", "none", "other"})


def _clean(value: str | None) -> str | None:
    """Trim to what the column holds; a blank or a shrug is absent."""
    cleaned = (value or "").strip()
    if not cleaned or cleaned.lower() in _NON_ANSWERS:
        return None
    return cleaned[:80]


async def classify_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    document_text: str,
    actor_user_id: uuid.UUID | None = None,
    gateway: ModelGateway | None = None,
    force: bool = False,
) -> str | None:
    """Record what this document is. Returns the type, or None.

    Runs for every document that parsed, whatever else the organization
    has or has not set up.

    Idempotent: a document that already carries a classification keeps it
    unless `force` is set. Re-classifying on every reprocess would ask a
    non-deterministic model the same question and take whatever it says
    this time — the same way re-extraction used to turn two evidence
    items into four.
    """
    if file_record.document_type and not force:
        return file_record.document_type

    if not document_text.strip():
        return None

    gateway = gateway or ModelGateway()
    raw = await gateway.generate_structured(
        db,
        organization_id=organization_id,
        requested_by=actor_user_id,
        request=GenerateRequest(
            task_type="compliance.document_classification",
            prompt=build_prompt(document_text),
            prompt_template="compliance_document_classification",
            prompt_version="1",
            input_classification="confidential",
        ),
        schema=DocumentClassification,
    )
    if not isinstance(raw, DocumentClassification):
        # Loud rather than quiet: an adapter returning the wrong shape
        # would otherwise look exactly like a document nobody could
        # classify.
        raise TypeError(
            "The AI provider returned an unexpected response shape for classification."
        )

    file_record.document_type = _clean(raw.document_type)
    file_record.document_domain = _clean(raw.document_domain)
    await db.flush()

    logger.info(
        "Classified %s as %s", file_record.id, file_record.document_type or "unclassified"
    )
    return file_record.document_type


__all__ = [
    "CLASSIFY_HEAD_CHARS",
    "DocumentClassification",
    "build_prompt",
    "classify_document",
]
