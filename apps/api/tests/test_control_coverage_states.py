"""The badge and the number beside it must agree.

`Apply technical and organisational security measures` shipped reading
"4 evidence items · 2 applicable requirements · Partially evidenced · 0%".
Partially evidenced and 0% are a contradiction: the status was decided in
one branch of the roll-up and the percentage in another, and nothing
checked them against each other.

The states are now ranges of the coverage figure rather than independent
judgements:

    evidenced              100%
    partially_evidenced    >0% and <100%
    evidence_insufficient  evidence exists, 0% demonstrated, cause known
    needs_review           evidence exists, 0% demonstrated, cause unclear
    no_evidence            no evidence items
    not_applicable         no applicable requirements

Most of these are asserted against the roll-up directly, because building
each shape through the document pipeline would test the model's mood
rather than this arithmetic. The end of the file walks the API to prove
the same states reach the screen.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.control_assessment import (
    ASSESSMENT_LABELS,
    ASSESSMENT_STATES,
    ZERO_COVERAGE_STATES,
    EvidenceProvenance,
    RequirementCoverageLine,
    _coverage_percent,
    _summarise,
)
from app.seed import _ensure_compliance_catalog


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


def _line(
    *,
    code: str,
    applicable: bool = True,
    coverage: str = "no_evidence",
    covered: bool = False,
    missing: list[str] | None = None,
) -> RequirementCoverageLine:
    return RequirementCoverageLine(
        requirement_id=uuid.uuid4(),
        reference_code=code,
        title=f"Requirement {code}",
        framework_key="gdpr",
        applicability="applicable" if applicable else "not_applicable",
        applicability_reason="",
        coverage="not_applicable" if not applicable else coverage,
        covered=covered,
        missing_conditions=missing or [],
    )


def _evidence(count: int) -> list[EvidenceProvenance]:
    return [
        EvidenceProvenance(
            evidence_id=uuid.uuid4(),
            file_id=uuid.uuid4(),
            filename=f"document-{index}.pdf",
            title=f"Document {index}",
            mapped_by="auto",
        )
        for index in range(count)
    ]


def _roll_up(lines: list[RequirementCoverageLine], evidence_count: int) -> tuple[str, int]:
    status, coverage, _why, _missing = _summarise(
        lines=lines, evidence=_evidence(evidence_count)
    )
    return status, coverage


# --- The reported contradiction ---------------------------------------


def test_four_documents_demonstrating_nothing_is_not_partially_evidenced() -> None:
    """The exact row from the report: 4 evidence items, 2 applicable
    requirements, nothing demonstrated."""
    status, coverage = _roll_up(
        [
            _line(code="Art. 32", coverage="deficient", missing=["Backup restoration test results"]),
            _line(code="A.10.2", coverage="deficient", missing=["Encryption configuration evidence"]),
        ],
        evidence_count=4,
    )
    assert coverage == 0
    assert status == "evidence_insufficient"
    assert ASSESSMENT_LABELS[status] == "Evidence insufficient"


def test_partially_evidenced_can_never_be_zero_or_one_hundred() -> None:
    """The invariant, asserted across every shape of control the roll-up
    can produce rather than for the one row that was reported."""
    for applicable in range(1, 7):
        for demonstrated in range(0, applicable + 1):
            for evidence_count in (0, 1, 5):
                lines = [
                    _line(
                        code=f"R{index}",
                        coverage="satisfied" if index < demonstrated else "deficient",
                        covered=index < demonstrated,
                        missing=[] if index < demonstrated else ["something"],
                    )
                    for index in range(applicable)
                ]
                status, coverage = _roll_up(lines, evidence_count)

                assert status in ASSESSMENT_STATES, status
                if status == "partially_evidenced":
                    assert 0 < coverage < 100, (applicable, demonstrated, coverage)
                elif status == "evidenced":
                    assert coverage == 100, (applicable, demonstrated, coverage)
                elif status in ZERO_COVERAGE_STATES:
                    assert coverage == 0, (status, applicable, demonstrated, coverage)


def test_rounding_can_never_contradict_the_status() -> None:
    """One covered of two hundred rounds to 0%, and one uncovered of two
    hundred rounds to 100%. Both would print a number that argues with
    the badge next to it."""
    assert _coverage_percent(1, 200) == 1
    assert _coverage_percent(199, 200) == 99
    assert _coverage_percent(0, 3) == 0
    assert _coverage_percent(3, 3) == 100
    assert _coverage_percent(0, 0) == 0


# --- The cases from the report ----------------------------------------


def test_four_evidence_two_requirements_none_demonstrated() -> None:
    status, coverage = _roll_up(
        [
            _line(code="Art. 32", coverage="deficient", missing=["x"]),
            _line(code="Art. 5", coverage="deficient", missing=["y"]),
        ],
        evidence_count=4,
    )
    assert (status, coverage) == ("evidence_insufficient", 0)


def test_four_evidence_two_requirements_one_demonstrated() -> None:
    status, coverage = _roll_up(
        [
            _line(code="Art. 32", coverage="satisfied", covered=True),
            _line(code="Art. 5", coverage="deficient", missing=["y"]),
        ],
        evidence_count=4,
    )
    assert (status, coverage) == ("partially_evidenced", 50)


def test_four_evidence_two_requirements_both_demonstrated() -> None:
    status, coverage = _roll_up(
        [
            _line(code="Art. 32", coverage="satisfied", covered=True),
            _line(code="Art. 5", coverage="satisfied", covered=True),
        ],
        evidence_count=4,
    )
    assert (status, coverage) == ("evidenced", 100)


def test_five_documents_all_supporting_one_of_three_requirements() -> None:
    """The case the report singles out: piling evidence onto the same
    obligation must not move the figure."""
    status, coverage = _roll_up(
        [
            _line(code="Art. 13", coverage="satisfied", covered=True),
            _line(code="Art. 14", coverage="deficient", missing=["y"]),
            _line(code="Art. 12", coverage="deficient", missing=["z"]),
        ],
        evidence_count=5,
    )
    assert (status, coverage) == ("partially_evidenced", 33)


def test_more_documents_on_the_same_requirement_do_not_raise_coverage() -> None:
    """Stated as a property: the figure is a function of the requirement
    lines alone, so the evidence count cannot enter it."""
    lines = [
        _line(code="Art. 13", coverage="satisfied", covered=True),
        _line(code="Art. 14", coverage="deficient", missing=["y"]),
        _line(code="Art. 12", coverage="deficient", missing=["z"]),
    ]
    figures = {_roll_up(lines, count)[1] for count in (1, 2, 5, 20, 100)}
    assert figures == {33}, figures


def test_no_evidence() -> None:
    status, coverage = _roll_up(
        [_line(code="Art. 32"), _line(code="Art. 5")], evidence_count=0
    )
    assert (status, coverage) == ("no_evidence", 0)


def test_no_applicable_requirements() -> None:
    status, coverage = _roll_up(
        [
            _line(code="Art. 72", applicable=False),
            _line(code="Art. 26", applicable=False),
        ],
        evidence_count=4,
    )
    assert (status, coverage) == ("not_applicable", 0)


def test_evidence_that_cannot_be_attributed_asks_rather_than_concludes() -> None:
    """Distinct from `evidence_insufficient`: both sit at 0%, but one
    names what is missing and the other cannot."""
    status, coverage = _roll_up(
        [
            _line(code="Art. 15", coverage="uncertain"),
            _line(code="9.1", coverage="uncertain"),
        ],
        evidence_count=4,
    )
    assert (status, coverage) == ("needs_review", 0)


def test_the_wording_matches_the_state() -> None:
    """A control at 0% must not be described as covering something."""
    _status, _coverage, why, missing = _summarise(
        lines=[
            _line(code="Art. 32", coverage="deficient", missing=["Backup restoration test results"]),
            _line(code="Art. 5", coverage="deficient", missing=["Retention schedule"]),
        ],
        evidence=_evidence(4),
    )
    assert "4 pieces of evidence are mapped" in why
    assert "covering" not in why
    assert "do not demonstrate any" in why
    assert missing and "Backup restoration test results" in missing


# --- The same states, through the API ---------------------------------


async def test_no_control_reaches_a_screen_in_a_contradictory_state(
    client: AsyncClient,
) -> None:
    """The roll-up is asserted above; this proves the states that reach a
    customer obey the same invariant, on both screens."""
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"coverage-{uuid.uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme Coverage {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text

    await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "operates_in_eu": True,
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "uses_third_party_ai": True,
            "builds_ai_features": True,
            "sells_to_enterprise": True,
        },
    )
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    for key in ("gdpr", "eu_ai_act", "iso42001"):
        framework_id = next(f["id"] for f in frameworks if f["key"] == key)
        await client.put(
            f"/api/v1/compliance/frameworks/{framework_id}/activation",
            json={"active": True},
        )

    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    assert len(controls) > 5

    for listed in controls:
        status = listed["assessment_status"]
        percent = listed["coverage_percent"]
        assert status in ASSESSMENT_STATES, (listed["title"], status)

        if status == "partially_evidenced":
            assert 0 < percent < 100, (listed["title"], percent)
        elif status == "evidenced":
            assert percent == 100, (listed["title"], percent)
        else:
            assert percent == 0, (listed["title"], status, percent)

        # The label is phrased server-side; the two screens must not
        # disagree about either half of the badge.
        detail = (await client.get(f"/api/v1/compliance/controls/{listed['id']}")).json()
        assert detail["assessment"]["status"] == status
        assert detail["assessment"]["confidence"] == percent
        assert detail["assessment"]["label"] == listed["assessment_label"]
        assert listed["assessment_label"] == ASSESSMENT_LABELS[status]
