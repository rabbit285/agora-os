"""Which requirements of an adopted framework actually bind you.

The false positive this exists to kill: Article 26 sets out obligations
for *deployers of high-risk AI systems*, and a company running one
limited-risk support chatbot is not in scope of it. Raising a
high-severity gap against them teaches people to ignore the gap list,
which is the most expensive thing this product can do to itself.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.framework_applicability import CompanyFacts
from app.compliance.models import AISystem
from app.compliance.requirement_applicability import (
    OrganizationProfile,
    evaluate_applicability,
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
            "full_name": "Scoping Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


def _system(**overrides: object) -> AISystem:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "organization_id": uuid.uuid4(),
        "name": "Customer Support AI",
        "purpose": "Draft replies.",
        "risk_classification": "limited",
        "deployment_status": "production",
        "is_external": True,
        "personal_data_processed": True,
        "sensitive_data_processed": False,
        "automated_decision_making": False,
        "third_party_vendors": [],
        "internal_users": [],
        "affected_users": [],
        "processed_data": [],
    }
    defaults.update(overrides)
    return AISystem(**defaults)  # type: ignore[arg-type]


DEPLOYER_ONLY = CompanyFacts(
    sells_to_eu_customers=True,
    processes_personal_data=True,
    uses_third_party_ai=True,
    builds_ai_features=False,
)


# --- The Article 26 case ---------------------------------------------


def test_article_26_does_not_apply_without_a_high_risk_system() -> None:
    profile = OrganizationProfile(facts=DEPLOYER_ONLY, ai_systems=[_system()])
    result = evaluate_applicability(
        profile, framework_key="eu_ai_act", reference_code="Art. 26"
    )
    assert result.applies is False
    # A "does not apply" verdict needs a reason as much as the opposite.
    assert "high-risk" in result.reason


def test_article_26_applies_once_a_high_risk_system_exists() -> None:
    profile = OrganizationProfile(
        facts=DEPLOYER_ONLY, ai_systems=[_system(risk_classification="high")]
    )
    result = evaluate_applicability(
        profile, framework_key="eu_ai_act", reference_code="Art. 26"
    )
    assert result.applies is True


def test_provider_obligations_do_not_bind_a_pure_deployer() -> None:
    """Articles 9-17 bind providers. Using OpenAI does not make you one."""
    profile = OrganizationProfile(
        facts=DEPLOYER_ONLY, ai_systems=[_system(risk_classification="high")]
    )
    for code in ("Art. 9", "Art. 10", "Art. 11", "Art. 16", "Art. 17", "Art. 72"):
        result = evaluate_applicability(
            profile, framework_key="eu_ai_act", reference_code=code
        )
        assert result.applies is False, code


def test_gpai_obligations_never_apply_by_default() -> None:
    """Building on someone else's model does not make you a general
    purpose AI model provider, and treating it that way would put a very
    heavy obligation on nearly every customer."""
    profile = OrganizationProfile(
        facts=CompanyFacts(builds_ai_features=True, sells_to_eu_customers=True),
        ai_systems=[_system(risk_classification="high")],
    )
    for code in ("Art. 53", "Art. 55"):
        assert (
            evaluate_applicability(
                profile, framework_key="eu_ai_act", reference_code=code
            ).applies
            is False
        )


def test_prohibited_practices_apply_to_anyone_touching_ai() -> None:
    profile = OrganizationProfile(facts=DEPLOYER_ONLY, ai_systems=[_system()])
    assert (
        evaluate_applicability(
            profile, framework_key="eu_ai_act", reference_code="Art. 5"
        ).applies
        is True
    )


def test_transparency_applies_only_to_customer_facing_ai() -> None:
    internal = OrganizationProfile(
        facts=DEPLOYER_ONLY, ai_systems=[_system(is_external=False)]
    )
    assert (
        evaluate_applicability(
            internal, framework_key="eu_ai_act", reference_code="Art. 50"
        ).applies
        is False
    )


# --- GDPR conditionals ------------------------------------------------


def test_article_9_applies_only_with_special_category_data() -> None:
    without = OrganizationProfile(facts=CompanyFacts(processes_personal_data=True))
    assert (
        evaluate_applicability(without, framework_key="gdpr", reference_code="Art. 9").applies
        is False
    )
    with_special = OrganizationProfile(
        facts=CompanyFacts(
            processes_personal_data=True, processes_special_category_data=True
        )
    )
    assert (
        evaluate_applicability(
            with_special, framework_key="gdpr", reference_code="Art. 9"
        ).applies
        is True
    )


def test_article_22_applies_only_with_automated_decisions() -> None:
    profile = OrganizationProfile(
        facts=DEPLOYER_ONLY, ai_systems=[_system(automated_decision_making=False)]
    )
    assert (
        evaluate_applicability(profile, framework_key="gdpr", reference_code="Art. 22").applies
        is False
    )
    deciding = OrganizationProfile(
        facts=DEPLOYER_ONLY, ai_systems=[_system(automated_decision_making=True)]
    )
    assert (
        evaluate_applicability(deciding, framework_key="gdpr", reference_code="Art. 22").applies
        is True
    )


def test_an_unlisted_requirement_applies_by_default() -> None:
    """Getting scope wrong toward "you have less to do" is worse than the
    reverse, so silence means in scope."""
    profile = OrganizationProfile(facts=CompanyFacts())
    assert (
        evaluate_applicability(profile, framework_key="gdpr", reference_code="Art. 30").applies
        is True
    )


def test_iso_42001_clauses_are_never_scoped_out() -> None:
    """A management system standard is adopted whole — you either run it
    or you do not."""
    profile = OrganizationProfile(facts=CompanyFacts())
    for code in ("4.1", "5.2", "6.1", "9.2", "10.1"):
        assert (
            evaluate_applicability(
                profile, framework_key="iso42001", reference_code=code
            ).applies
            is True
        )


# --- End to end: no gap, no score penalty -----------------------------


async def test_a_non_applicable_requirement_creates_no_gap_and_no_penalty(
    client: AsyncClient,
) -> None:
    """The whole point. A company deploying one limited-risk chatbot must
    not be told it has a high-severity Article 26 finding, and must not be
    scored down for an article that does not bind it."""
    await _signup(client, "scope-e2e@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "uses_third_party_ai": True,
        },
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Customer Support AI",
            "purpose": "Draft replies from the knowledge base.",
            "risk_classification": "limited",
        },
    )

    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    ai_act = next(f for f in frameworks if f["key"] == "eu_ai_act")
    await client.put(
        f"/api/v1/compliance/frameworks/{ai_act['id']}/activation", json={"active": True}
    )

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{ai_act['id']}/assess")
    ).json()
    by_code = {r["reference_code"]: r for r in result["requirements"]}

    # Article 26 is reported as out of scope, with the reason...
    assert by_code["Art. 26"]["status"] == "not_applicable"
    assert by_code["Art. 26"]["summary"]
    # ...produces no gap...
    assert by_code["Art. 26"]["gap_id"] is None
    gaps = (await client.get("/api/v1/compliance/gaps")).json()
    assert all(g["requirement_id"] != by_code["Art. 26"]["requirement_id"] for g in gaps)

    # ...and is excluded from the denominator rather than counted as failed.
    readiness = result["readiness"]
    assert readiness["total"] < len(result["requirements"])
    assert "do not apply" in readiness["explanation"]


async def test_scoping_out_requirements_does_not_inflate_readiness(
    client: AsyncClient,
) -> None:
    """A company in scope of fewer articles must not score higher than one
    that actually evidenced them — non-applicable requirements leave the
    denominator, they do not count as passes."""
    await _signup(client, "scope-noinflate@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={"sells_to_eu_customers": True, "uses_third_party_ai": True},
    )
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    ai_act = next(f for f in frameworks if f["key"] == "eu_ai_act")
    await client.put(
        f"/api/v1/compliance/frameworks/{ai_act['id']}/activation", json={"active": True}
    )

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{ai_act['id']}/assess")
    ).json()
    # No evidence has been supplied, so nothing is satisfied regardless of
    # how many articles were scoped out.
    assert result["readiness"]["percent"] == 0.0
    assert result["readiness"]["satisfied"] == 0
