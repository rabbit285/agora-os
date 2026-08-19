"""Which frameworks apply, and why.

The question the customer cannot answer on their own. These tests exist
because the answer has to be *arguable*: every recommendation traces to a
fact the organization declared, so disagreeing with a recommendation
means disagreeing with a fact and changing it — not appealing to a model.

No test here calls a provider. Applicability is rules over declared
facts, deliberately, and a test that varied with model output would be
testing the wrong thing.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.framework_applicability import (
    CompanyFacts,
    applicable_framework_keys,
    recommend_frameworks,
)
from app.seed import _ensure_compliance_catalog


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


async def _signup(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Applicability Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


# The customer this product is for: a US software company with EU
# customers that builds AI features on a third-party model.
ICP = CompanyFacts(
    operates_in_eu=False,
    sells_to_eu_customers=True,
    processes_personal_data=True,
    uses_third_party_ai=True,
    builds_ai_features=True,
    is_data_processor=True,
    sells_to_enterprise=True,
    sector="saas",
    employee_count_range="51-200",
)


def _by_key(facts: CompanyFacts) -> dict[str, object]:
    return {r.framework_key: r for r in recommend_frameworks(facts)}


# --- The rules -------------------------------------------------------


def test_the_target_customer_gets_gdpr_and_the_ai_act_as_required() -> None:
    result = _by_key(ICP)
    assert result["gdpr"].applicability == "required"  # type: ignore[attr-defined]
    assert result["eu_ai_act"].applicability == "required"  # type: ignore[attr-defined]
    assert result["iso42001"].applicability == "recommended"  # type: ignore[attr-defined]


def test_every_recommendation_states_the_facts_it_rests_on() -> None:
    """A recommendation without a reason is a guess wearing a badge."""
    for recommendation in recommend_frameworks(ICP):
        if recommendation.applicability != "not_indicated":
            assert recommendation.reasons, f"{recommendation.framework_key} gave no reason"


def test_nothing_declared_puts_nothing_in_scope() -> None:
    """An unanswered question must never manufacture an obligation."""
    assert applicable_framework_keys(CompanyFacts()) == []


def test_personal_data_without_an_eu_nexus_is_not_asserted_as_required() -> None:
    """Article 3 can still reach them, so this is flagged for review
    rather than either asserted or dismissed."""
    facts = CompanyFacts(processes_personal_data=True)
    gdpr = _by_key(facts)["gdpr"]
    assert gdpr.applicability == "recommended"  # type: ignore[attr-defined]
    assert gdpr.requires_legal_review is True  # type: ignore[attr-defined]
    assert gdpr.uncertainties  # type: ignore[attr-defined]


def test_no_ai_means_the_ai_act_is_not_indicated() -> None:
    facts = CompanyFacts(processes_personal_data=True, sells_to_eu_customers=True)
    assert _by_key(facts)["eu_ai_act"].applicability == "not_indicated"  # type: ignore[attr-defined]


def test_nis2_is_never_asserted_as_required() -> None:
    """Scope turns on sector annexes and national implementation that a
    signup form cannot settle. Telling a company they are out of scope
    when they are not is the most expensive mistake available here."""
    facts = CompanyFacts(
        operates_in_eu=True, sector="digital_infrastructure", employee_count_range="201-1000"
    )
    nis2 = _by_key(facts)["nis2"]
    assert nis2.applicability == "likely"  # type: ignore[attr-defined]
    assert nis2.requires_legal_review is True  # type: ignore[attr-defined]


def test_special_category_data_is_called_out_on_gdpr() -> None:
    facts = CompanyFacts(
        processes_personal_data=True,
        processes_special_category_data=True,
        operates_in_eu=True,
    )
    reasons = " ".join(_by_key(facts)["gdpr"].reasons)  # type: ignore[attr-defined]
    assert "Article 9" in reasons


def test_no_recommendation_claims_the_organization_is_compliant() -> None:
    """Applicability says a framework is in scope. It says nothing about
    whether the organization meets it — that is the assessment's job, from
    evidence."""
    for facts in (ICP, CompanyFacts(processes_personal_data=True, operates_in_eu=True)):
        for recommendation in recommend_frameworks(facts):
            text = " ".join(recommendation.reasons + recommendation.uncertainties).lower()
            for forbidden in ("you are compliant", "compliant with", "violation", "non-compliant"):
                assert forbidden not in text


# --- The endpoints ---------------------------------------------------


async def test_declaring_facts_returns_the_recommendations(client: AsyncClient) -> None:
    await _signup(client, "applicability-declare@example.com")

    response = await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "uses_third_party_ai": True,
            "builds_ai_features": True,
            "sells_to_enterprise": True,
            "sector": "saas",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["facts_declared"] is True
    by_key = {r["framework_key"]: r for r in body["recommendations"]}
    assert by_key["gdpr"]["applicability"] == "required"
    assert by_key["eu_ai_act"]["applicability"] == "required"
    assert by_key["gdpr"]["reasons"]


async def test_recommendations_before_anything_is_declared_are_not_a_verdict(
    client: AsyncClient,
) -> None:
    """An empty result must be presented as "we have not asked yet", not
    as "nothing applies to you" — which is the one wrong answer here."""
    await _signup(client, "applicability-empty@example.com")
    body = (await client.get("/api/v1/compliance/framework-recommendations")).json()
    assert body["facts_declared"] is False
    assert all(r["applicability"] == "not_indicated" for r in body["recommendations"])


async def test_adopting_recommended_frameworks_activates_and_scaffolds(
    client: AsyncClient,
) -> None:
    await _signup(client, "applicability-adopt@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "builds_ai_features": True,
        },
    )

    response = await client.post(
        "/api/v1/compliance/frameworks/adopt-recommended",
        json={"framework_keys": ["gdpr", "eu_ai_act"]},
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
    controls = (await client.get("/api/v1/compliance/controls")).json()
    assert controls, "adopting recommended frameworks scaffolded no controls"


async def test_adopting_an_unknown_framework_is_rejected(client: AsyncClient) -> None:
    await _signup(client, "applicability-unknown@example.com")
    response = await client.post(
        "/api/v1/compliance/frameworks/adopt-recommended",
        json={"framework_keys": ["not_a_real_framework"]},
    )
    assert response.status_code == 404


async def test_company_facts_are_tenant_scoped(client: AsyncClient) -> None:
    await _signup(client, "applicability-tenant-a@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={"processes_personal_data": True, "operates_in_eu": True},
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "applicability-tenant-b@example.com")
    body = (await client.get("/api/v1/compliance/framework-recommendations")).json()
    assert body["facts_declared"] is False
