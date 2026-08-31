from __future__ import annotations

import uuid

from pydantic import BaseModel


class CitationOut(BaseModel):
    """One source, in terms the customer can act on.

    Deliberately has no `chunk_id`, `chunk_index` or `score` field. Those
    exist — every retrieved chunk is recorded against the AI request by id
    for traceability (app.ai.models.AIRequest.citations) — but they are
    ours: a chunk number is an artefact of slicing a file into fixed-size
    windows, and nobody can find "chunk 5" in their own copy of a PDF.
    What they can find is a heading and a page.

    `document_id` is the one identifier that survives, and only because
    clicking a citation has to open something. It is a link target, never
    text to render.

    `href` is composed server-side too. The frontend used to build it, and
    went on pointing at `/knowledge/<id>` long after that module was
    withdrawn — a dead link the API had no way to notice, because it was
    returning a perfectly valid citation. One resolver owns the route now
    (app.ai.citations.DOCUMENT_ROUTE).
    """

    # "AI Governance Policy — §7 Monitoring". Pre-composed server-side so
    # every surface that shows a citation shows the same thing.
    reference: str
    document_title: str
    section: str | None = None
    page: int | None = None
    # The passage the answer actually rests on, elided at the ends where
    # the chunk boundary cut a sentence.
    passage: str
    source_type: str | None = None
    document_id: uuid.UUID
    # Ready to put in an href. Carries the passage so the reader opens at
    # it rather than at the top of the document.
    href: str


class ComplianceFactOut(BaseModel):
    """A value read from Veyntra's compliance records, not from a document.

    Kept in its own list rather than mixed into `citations` because the
    two answer different questions. "Current status: Needs review" is a
    determination this product made from declared facts and evidence; no
    uploaded document says it, and filing it under a document citation
    would tell the customer to go argue with a PDF about it.
    """

    label: str
    value: str
    detail: str | None = None


class CopilotAskRequest(BaseModel):
    prompt: str


class CopilotAskResponse(BaseModel):
    text: str
    provider: str
    model: str
    grounded: bool
    # Where the answer came from, kept apart: `facts` is Veyntra's own
    # records, `citations` is what uploaded documents say.
    facts: list[ComplianceFactOut] = []
    citations: list[CitationOut]


class AIProviderStatusOut(BaseModel):
    provider_key: str
    name: str
    has_adapter: bool
    configured: bool
    active: bool
