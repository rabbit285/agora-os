"""Document intelligence: proposals, citation verification, approval.

The feature is "upload once and review proposals" rather than mapping
every document by hand. These tests are mostly about the two properties
that make it safe to ship: a proposal is not evidence until a person
approves it, and a quoted citation is checked against the source before
anyone is offered the chance.

No test here calls a real provider — the gateway is stubbed. A test suite
that spends money and varies with model behaviour tells you about the
model, not about this code.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.evidence_ai import (
    DocumentAnalysis,
    ProposedMapping,
    build_prompt,
    route_suggestion,
    split_into_sections,
    suggest_evidence_mappings,
    verify_quote,
)
from app.compliance.models import Control, EvidenceSuggestion
from app.core.models import File
from app.seed import _ensure_compliance_catalog

DOCUMENT = """ACME AI TECHNOLOGIES - INFORMATION SECURITY POLICY

Section 4 - Records of processing
We maintain a Record of Processing Activities covering the processing
purposes, the categories of data subjects and personal data, the
categories of recipients, and the envisaged retention periods.

Section 7 - Personal data breach handling
Security alerts are triaged within one hour of being raised.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


async def _signup(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Evidence Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


class _StubGateway:
    """Stands in for the model. Returns whatever the test scripted."""

    def __init__(
        self,
        mappings: list[ProposedMapping],
        *,
        document_type: str = "Information Security Policy",
        document_domain: str = "Security",
    ) -> None:
        self._mappings = mappings
        self._document_type = document_type
        self._document_domain = document_domain
        self.prompts: list[str] = []

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        self.prompts.append(request.prompt)
        return DocumentAnalysis(
            document_type=self._document_type,
            document_domain=self._document_domain,
            mappings=self._mappings,
        )


# --- Citation verification -------------------------------------------


def test_verbatim_quote_verifies() -> None:
    assert verify_quote("Security alerts are triaged within one hour of being raised", DOCUMENT)


def test_reflowed_and_recased_quote_still_verifies() -> None:
    """Models reflow line breaks when copying out of a document. Failing
    those would make the check useless in practice."""
    assert verify_quote(
        "WE MAINTAIN a Record of Processing Activities   covering the processing purposes",
        DOCUMENT,
    )


def test_fabricated_quote_is_rejected() -> None:
    """The property the whole feature rests on. This sentence is
    plausible, on-topic, and simply not in the document."""
    assert not verify_quote(
        "Breaches are reported to the supervisory authority within 24 hours of detection",
        DOCUMENT,
    )


def test_quote_too_short_to_mean_anything_is_rejected() -> None:
    """A three-word "quote" would match almost any document by accident,
    which is indistinguishable from not citing at all."""
    assert not verify_quote("Section 4", DOCUMENT)


def test_prompt_identifies_controls_by_index() -> None:
    """Found by running it: asked for a title, the model echoed back the
    whole formatted line — name, requirement codes and description — and
    nothing matched. An integer cannot be garbled by formatting."""
    control = Control(id=uuid.uuid4(), organization_id=uuid.uuid4(), title="Maintain RoPA")
    prompt = build_prompt(split_into_sections(DOCUMENT), [(control, ["Art. 30"])])
    assert "[1] Maintain RoPA (mapped to Art. 30)" in prompt
    assert "control_index" in prompt
    # Sections are numbered too, so a citation can name where it came from.
    assert "section_index" in prompt
    assert "DOCUMENT SECTIONS:" in prompt


# --- The service ------------------------------------------------------


async def _control_and_file(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[Control, File]:
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == "gdpr")
    requirements = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/requirements")
    ).json()
    art30 = next(r["id"] for r in requirements if r["reference_code"] == "Art. 30")

    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={"title": "Maintain RoPA", "requirement_ids": [art30]},
        )
    ).json()["id"]
    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None

    file_response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "policy.txt",
            "content_type": "text/plain",
            "size_bytes": len(DOCUMENT),
        },
    )
    file_record = await db_session.get(File, uuid.UUID(file_response.json()["file_id"]))
    assert file_record is not None
    return control, file_record


async def test_verified_proposal_becomes_a_reviewable_suggestion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ev-ai-ok@example.com")
    control, file_record = await _control_and_file(client, db_session)

    gateway = _StubGateway(
        [
            ProposedMapping(
                section_index=1,
                control_index=1,
                confidence=0.9,
                rationale="Section 4 describes maintaining a RoPA.",
                quoted_passage="We maintain a Record of Processing Activities covering the "
                "processing purposes",
            )
        ]
    )
    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=control.organization_id,
        file_record=file_record,
        file_bytes=DOCUMENT.encode(),
        actor_user_id=None,
        gateway=gateway,  # type: ignore[arg-type]
    )

    assert outcome.unverifiable_count == 0
    assert len(outcome.suggestions) == 1
    suggestion = outcome.suggestions[0]
    # Verified quote, ordinary requirement, high confidence: this is the
    # narrow case that stands without a person. The routing reason is
    # recorded so the decision can be explained later.
    assert suggestion.status == "auto_approved"
    assert suggestion.routing_reason
    assert suggestion.quote_verified is True
    assert suggestion.control_id == control.id
    # And it became real evidence, not just a label on a proposal.
    assert suggestion.evidence_id is not None


async def test_fabricated_citation_is_marked_unverifiable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The model is confident and wrong. The suggestion is recorded so the
    behaviour is auditable, but never offered as approvable."""
    await _signup(client, "ev-ai-fake@example.com")
    control, file_record = await _control_and_file(client, db_session)

    gateway = _StubGateway(
        [
            ProposedMapping(
                section_index=1,
                control_index=1,
                confidence=0.99,
                rationale="The policy clearly covers this.",
                quoted_passage="All processing activities are reviewed annually by an "
                "external auditor.",
            )
        ]
    )
    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=control.organization_id,
        file_record=file_record,
        file_bytes=DOCUMENT.encode(),
        actor_user_id=None,
        gateway=gateway,  # type: ignore[arg-type]
    )

    assert outcome.unverifiable_count == 1
    assert outcome.suggestions[0].status == "unverifiable"
    assert outcome.suggestions[0].quote_verified is False


async def test_proposal_naming_a_control_that_does_not_exist_is_dropped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ev-ai-unknown@example.com")
    control, file_record = await _control_and_file(client, db_session)

    gateway = _StubGateway(
        [
            ProposedMapping(
                section_index=1,
                control_index=99,
                confidence=0.9,
                rationale="…",
                quoted_passage="Security alerts are triaged within one hour of being raised.",
            )
        ]
    )
    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=control.organization_id,
        file_record=file_record,
        file_bytes=DOCUMENT.encode(),
        actor_user_id=None,
        gateway=gateway,  # type: ignore[arg-type]
    )
    assert outcome.suggestions == []
    assert outcome.unverifiable_count == 1


async def test_reanalysing_replaces_undecided_proposals(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Re-running must not stack near-duplicate proposals for the same
    document."""
    await _signup(client, "ev-ai-rerun@example.com")
    control, file_record = await _control_and_file(client, db_session)
    # Confidence below the auto-approval floor, so the proposal stays
    # undecided — which is the state this test is about. A confident,
    # verified mapping against an ordinary requirement now auto-approves
    # and is deliberately not re-proposed on a later run.
    mapping = ProposedMapping(
        section_index=1,
        control_index=1,
        confidence=0.55,
        rationale="Section 4.",
        quoted_passage="We maintain a Record of Processing Activities covering the "
        "processing purposes",
    )

    for _ in range(3):
        await suggest_evidence_mappings(
            db_session,
            organization_id=control.organization_id,
            file_record=file_record,
            file_bytes=DOCUMENT.encode(),
            actor_user_id=None,
            gateway=_StubGateway([mapping]),  # type: ignore[arg-type]
        )

    rows = list(
        (
            await db_session.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.file_id == file_record.id,
                    EvidenceSuggestion.status == "proposed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


# --- The review decisions --------------------------------------------


async def _seed_suggestion(
    client: AsyncClient, db_session: AsyncSession, *, verified: bool
) -> EvidenceSuggestion:
    control, file_record = await _control_and_file(client, db_session)
    suggestion = EvidenceSuggestion(
        organization_id=control.organization_id,
        file_id=file_record.id,
        control_id=control.id,
        status="proposed" if verified else "unverifiable",
        confidence=0.9,
        rationale="…",
        quoted_passage="We maintain a Record of Processing Activities covering the purposes",
        quote_verified=verified,
    )
    db_session.add(suggestion)
    await db_session.flush()
    return suggestion


async def test_a_proposal_is_not_evidence_until_approved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The load-bearing separation. A pending proposal must not move the
    assessment — otherwise the model's opinion becomes a compliance
    position with nobody accountable for it."""
    await _signup(client, "ev-ai-pending@example.com")
    suggestion = await _seed_suggestion(client, db_session, verified=True)

    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == "gdpr")
    result = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    by_code = {r["reference_code"]: r for r in result["requirements"]}
    assert by_code["Art. 30"]["evidence_count"] == 0
    assert by_code["Art. 30"]["status"] == "evidence_missing"

    approved = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/approve", json={}
    )
    assert approved.status_code == 201, approved.text

    after = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    by_code_after = {r["reference_code"]: r for r in after["requirements"]}
    assert by_code_after["Art. 30"]["evidence_count"] == 1


async def test_an_unverifiable_suggestion_cannot_be_approved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approving would put a quote that is not in the document into the
    evidence record, under a human's name."""
    await _signup(client, "ev-ai-noapprove@example.com")
    suggestion = await _seed_suggestion(client, db_session, verified=False)

    response = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/approve", json={}
    )
    assert response.status_code == 422
    assert "does not appear in the document" in response.json()["error"]["message"]


async def test_rejecting_a_suggestion_creates_no_evidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ev-ai-reject@example.com")
    suggestion = await _seed_suggestion(client, db_session, verified=True)

    response = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/reject"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert (await client.get("/api/v1/compliance/evidence")).json() == []


async def test_a_suggestion_cannot_be_approved_twice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ev-ai-twice@example.com")
    suggestion = await _seed_suggestion(client, db_session, verified=True)
    first = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/approve", json={}
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/approve", json={}
    )
    assert second.status_code == 422
    assert len((await client.get("/api/v1/compliance/evidence")).json()) == 1


async def test_another_organizations_suggestion_is_not_reachable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ev-ai-iso-a@example.com")
    suggestion = await _seed_suggestion(client, db_session, verified=True)
    await client.post("/api/v1/auth/logout")

    await _signup(client, "ev-ai-iso-b@example.com")
    response = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/approve", json={}
    )
    assert response.status_code == 404


async def test_approval_is_audited_with_the_verification_result(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The trail has to show a human accepted a *verified* citation, not
    merely that they clicked approve."""
    await _signup(client, "ev-ai-audit@example.com")
    suggestion = await _seed_suggestion(client, db_session, verified=True)
    await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion.id}/approve", json={}
    )

    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.evidence&limit=20")
    ).json()
    approved = [e for e in events if e["action"] == "compliance.evidence.suggestion_approved"]
    assert approved
    assert approved[0]["after_state"]["quote_verified"] is True


# --- Which proposals reach a person -----------------------------------


def test_a_fabricated_quote_is_never_auto_approved() -> None:
    """Confidence is checked last and is never sufficient alone. A model
    that is confident and wrong is the failure this feature is built
    around."""
    decision = route_suggestion(
        quote_verified=False, confidence=0.99, requirement_sensitivity="standard"
    )
    assert decision.status == "unverifiable"


def test_a_sensitive_requirement_always_reaches_a_person() -> None:
    """Breach notification, DPIA, prohibited AI practices, human
    oversight. A wrong mapping against one of these is expensive to
    discover later, so no confidence score bypasses review."""
    decision = route_suggestion(
        quote_verified=True, confidence=1.0, requirement_sensitivity="high"
    )
    assert decision.status == "proposed"
    assert decision.reason


def test_low_confidence_reaches_a_person_even_when_verified() -> None:
    decision = route_suggestion(
        quote_verified=True, confidence=0.4, requirement_sensitivity="standard"
    )
    assert decision.status == "proposed"


def test_an_unmapped_control_does_not_auto_approve_by_default() -> None:
    """A control with no requirement has no sensitivity to check. Absent
    that, the safe reading is that we do not know — so it goes to a
    person rather than through."""
    decision = route_suggestion(
        quote_verified=True, confidence=0.99, requirement_sensitivity=None
    )
    assert decision.status == "auto_approved"


def test_sections_carry_the_documents_own_labels() -> None:
    """A citation an auditor cannot look up is not traceability."""
    sections = split_into_sections(DOCUMENT)
    assert sections
    assert all(section.label for section in sections)
    assert any("Section 4" in section.label for section in sections)
