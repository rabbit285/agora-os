"""Which requirements of an adopted framework actually apply.

Adopting a framework does not mean every article in it binds you. The EU
AI Act is the clearest case: Article 26 sets out obligations for
*deployers of high-risk AI systems*. An organization with one
limited-risk support chatbot is not in scope of it, and generating a
high-severity gap against them for it is a false positive that teaches
people to ignore the gap list — which is the most expensive thing this
product can do to itself.

**Rules over declared facts, never a model call.** Applicability is a
legal scoping question with a mostly mechanical answer given the facts:
what the organization does, what AI it runs, and how that AI is
classified. Each rule states the condition it tested, so a customer who
disagrees can change the fact rather than argue with a black box.

**Silence means it applies.** A requirement with no rule is in scope by
default. Getting scope wrong in the direction of "you have less to do
than you thought" is far worse than the reverse, so a requirement only
drops out when a rule explicitly says why.

**Not applicable is not satisfied.** These requirements are excluded from
the readiness denominator entirely rather than counted as passing — a
company in scope of fewer articles should not score higher than one that
evidenced them.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.framework_applicability import CompanyFacts
from app.compliance.models import AISystem

HIGH_RISK_TIERS = frozenset({"high", "unacceptable"})
LIVE_DEPLOYMENT = frozenset({"pilot", "production"})


@dataclass
class OrganizationProfile:
    """Everything the scoping rules read, gathered once.

    Assembled from declared company facts plus the AI system inventory,
    because the two answer different halves of the question: the facts say
    what the company is, the inventory says what it actually runs.
    """

    facts: CompanyFacts
    ai_systems: list[AISystem] = field(default_factory=list)
    # Whether the organization has actually declared its facts. Without
    # this an empty profile is indistinguishable from one that answered
    # "no" to everything — and answering every scoping rule "does not
    # apply" for a customer who has told us nothing produces a framework
    # that is vacuously complete.
    facts_declared: bool = True

    def scoped_to(self, system: AISystem) -> OrganizationProfile:
        """The same organization, considering only one of its systems.

        Every rule below is written against the profile's aggregate
        properties, so narrowing the inventory to a single system makes
        all of them answer per-system without being rewritten. That is
        the whole mechanism behind Art. 72 applying to one AI system and
        not to another in the same company.
        """
        return OrganizationProfile(
            facts=self.facts, ai_systems=[system], facts_declared=self.facts_declared
        )

    @property
    def has_ai(self) -> bool:
        return bool(self.ai_systems) or self.facts.touches_ai

    @property
    def is_provider(self) -> bool:
        """Builds AI into a product it puts on the market."""
        return self.facts.builds_ai_features

    @property
    def is_deployer(self) -> bool:
        """Uses an AI system under its own authority."""
        return self.facts.uses_third_party_ai or bool(self.ai_systems)

    @property
    def high_risk_systems(self) -> list[AISystem]:
        return [s for s in self.ai_systems if s.risk_classification in HIGH_RISK_TIERS]

    @property
    def has_high_risk_ai(self) -> bool:
        return bool(self.high_risk_systems)

    @property
    def has_external_ai(self) -> bool:
        """AI that people outside the organization interact with."""
        return any(s.is_external for s in self.ai_systems)

    @property
    def has_automated_decisions(self) -> bool:
        return any(s.automated_decision_making for s in self.ai_systems)

    @property
    def ai_reaches_eu(self) -> bool:
        return self.facts.has_eu_nexus


# Four answers, not two. `needs_review` is the one that was missing:
# without it, "we cannot tell whether this binds you" was recorded as
# "it does not bind you", which quietly shrinks the denominator and
# flatters the score. Only `not_applicable` is ever excluded from
# coverage and readiness — the other three all count.
APPLICABILITY_STATUSES = (
    "applicable",
    "likely_applicable",
    "needs_review",
    "not_applicable",
)

COUNTED_STATUSES = frozenset({"applicable", "likely_applicable", "needs_review"})


@dataclass
class RequirementApplicability:
    reference_code: str
    applies: bool
    # Why, in the customer's own facts. Present whether it applies or not:
    # "this does not apply to you" needs a reason as much as the opposite.
    reason: str
    status: str = "applicable"
    # The systems this requirement binds, where it is system-dependent.
    # Empty for organization-level obligations.
    system_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def counts_toward_coverage(self) -> bool:
        return self.status in COUNTED_STATUSES


# A rule returns (applies, reason). Keyed by (framework_key,
# reference_code). Anything unlisted applies by default.
_Rule = Callable[[OrganizationProfile], tuple[bool, str]]


def _high_risk_provider(profile: OrganizationProfile) -> tuple[bool, str]:
    if profile.is_provider and profile.has_high_risk_ai:
        return True, "You build AI features and have a system classified high risk."
    if not profile.is_provider:
        return (
            False,
            "This binds providers of high-risk AI systems. You have not declared that you "
            "build AI features into a product you place on the market.",
        )
    return (
        False,
        "This binds providers of high-risk AI systems. None of your registered AI systems "
        "is classified high risk.",
    )


def _high_risk_deployer(profile: OrganizationProfile) -> tuple[bool, str]:
    if profile.is_deployer and profile.has_high_risk_ai:
        return True, "You operate an AI system classified high risk."
    if not profile.is_deployer:
        return False, "This binds deployers of high-risk AI systems. You run none."
    return (
        False,
        "This binds deployers of high-risk AI systems. None of your registered AI systems "
        "is classified high risk — register or reclassify one and this will apply.",
    )


def _high_risk_provider_in_market(profile: OrganizationProfile) -> tuple[bool, str]:
    """Post-market obligations, which begin at the market.

    Article 72 asks providers to monitor systems they have *placed on
    the market*. A high-risk system still in development is squarely
    subject to the design-time articles and not yet to this one, and
    collapsing the two would raise a finding for monitoring that cannot
    exist yet. This is also where the per-system model earns itself: the
    same company can owe post-market monitoring for a live engine and
    not for the one still being built.
    """
    live = [
        system
        for system in profile.high_risk_systems
        if system.deployment_status in LIVE_DEPLOYMENT
    ]
    if profile.is_provider and live:
        return True, "You place a high-risk AI system on the market."
    if not profile.is_provider:
        return (
            False,
            "This binds providers of high-risk AI systems after they are placed on the "
            "market. You have not declared that you build AI features into a product you "
            "place on the market.",
        )
    if not profile.high_risk_systems:
        return (
            False,
            "This binds post-market monitoring of high-risk AI systems. None of your "
            "registered AI systems is classified high risk.",
        )
    return (
        False,
        "This begins once a high-risk system is placed on the market. Your high-risk "
        "systems are still in development — this will apply when one goes live.",
    )


def _any_ai(profile: OrganizationProfile) -> tuple[bool, str]:
    if profile.has_ai:
        return True, "You use or build AI systems."
    return False, "You have not declared any use of AI."


def _external_ai(profile: OrganizationProfile) -> tuple[bool, str]:
    if profile.has_external_ai:
        return True, "People outside your organization interact with one of your AI systems."
    if profile.has_ai:
        return (
            False,
            "This covers AI that people interact with directly. None of your registered "
            "systems is marked as customer-facing.",
        )
    return False, "You have not declared any use of AI."


def _gpai_provider(profile: OrganizationProfile) -> tuple[bool, str]:
    # Deliberately narrow. Building a product on top of someone else's
    # model does not make you a general-purpose AI model provider, and
    # treating it that way would put a very heavy obligation on almost
    # every customer this product has.
    return (
        False,
        "This binds providers of general-purpose AI models. Building on a third-party model "
        "does not make you one. Mark this applicable manually if you train and release one.",
    )


def _special_category(profile: OrganizationProfile) -> tuple[bool, str]:
    if profile.facts.processes_special_category_data:
        return True, "You declared that you process special category data."
    return (
        False,
        "You have not declared processing of special category data (health, biometrics, "
        "religion, political opinions, sexual orientation, trade union membership).",
    )


def _automated_decisions(profile: OrganizationProfile) -> tuple[bool, str]:
    if profile.has_automated_decisions:
        return True, "One of your AI systems makes automated decisions about people."
    if profile.facts.processes_personal_data and profile.has_ai:
        return (
            False,
            "None of your registered AI systems is marked as making automated decisions "
            "with legal or similarly significant effects.",
        )
    return False, "You have not declared automated decision-making about individuals."


def _international_transfers(profile: OrganizationProfile) -> tuple[bool, str]:
    # A company with no EU establishment that sells into the EU is by
    # definition moving data out of it.
    if profile.facts.sells_to_eu_customers and not profile.facts.operates_in_eu:
        return (
            True,
            "You serve EU customers without an EU establishment, so personal data leaves "
            "the Union.",
        )
    if profile.facts.operates_in_eu:
        return (
            True,
            "You operate in the EU, so any processing outside it is a transfer.",
        )
    return False, "You have not declared EU operations or EU customers."


_RULES: dict[tuple[str, str], _Rule] = {
    # --- EU AI Act ---------------------------------------------------
    ("eu_ai_act", "Art. 4"): _any_ai,
    ("eu_ai_act", "Art. 5"): _any_ai,
    ("eu_ai_act", "Art. 6"): _any_ai,
    ("eu_ai_act", "Art. 9"): _high_risk_provider,
    ("eu_ai_act", "Art. 10"): _high_risk_provider,
    ("eu_ai_act", "Art. 11"): _high_risk_provider,
    ("eu_ai_act", "Art. 12"): _high_risk_provider,
    ("eu_ai_act", "Art. 13"): _high_risk_provider,
    ("eu_ai_act", "Art. 14"): _high_risk_deployer,
    ("eu_ai_act", "Art. 15"): _high_risk_provider,
    ("eu_ai_act", "Art. 16"): _high_risk_provider,
    ("eu_ai_act", "Art. 17"): _high_risk_provider,
    ("eu_ai_act", "Art. 26"): _high_risk_deployer,
    ("eu_ai_act", "Art. 27"): _high_risk_deployer,
    ("eu_ai_act", "Art. 50"): _external_ai,
    ("eu_ai_act", "Art. 53"): _gpai_provider,
    ("eu_ai_act", "Art. 55"): _gpai_provider,
    ("eu_ai_act", "Art. 72"): _high_risk_provider_in_market,
    # --- GDPR ---------------------------------------------------------
    ("gdpr", "Art. 9"): _special_category,
    ("gdpr", "Art. 22"): _automated_decisions,
    ("gdpr", "Art. 44"): _international_transfers,
    # Everything else in GDPR applies once GDPR applies. Article 30's
    # small-organization exemption is deliberately not modelled: it is
    # narrow, conditional, and almost never actually available to a SaaS
    # company processing customer data.
    # --- ISO 42001 ----------------------------------------------------
    # A management system standard is adopted whole. There is no clause
    # you are exempt from because of what you are; you either run the
    # management system or you do not.
}


async def load_profile(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    facts: CompanyFacts,
    facts_declared: bool = True,
) -> OrganizationProfile:
    systems = list(
        (
            await db.execute(
                select(AISystem).where(AISystem.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    return OrganizationProfile(
        facts=facts, ai_systems=systems, facts_declared=facts_declared
    )


def _is_system_dependent(framework_key: str, reference_code: str) -> bool:
    """Whether this requirement's answer can differ per AI system."""
    return _RULES.get((framework_key, reference_code)) in _SYSTEM_RULES


# Rules that read the inventory, and can therefore differ per system.
# Listed rather than inferred so adding a rule forces a deliberate
# decision about whether it is system-dependent.
_SYSTEM_RULES = frozenset(
    {
        _high_risk_provider,
        _high_risk_provider_in_market,
        _high_risk_deployer,
        _any_ai,
        _external_ai,
        _automated_decisions,
    }
)


def evaluate_applicability(
    profile: OrganizationProfile, *, framework_key: str, reference_code: str
) -> RequirementApplicability:
    """Does this requirement bind this organization?

    System-dependent obligations are resolved against each registered
    system in turn and bind the organization if they bind any one of
    them — so a company can be subject to Art. 72 for its credit-scoring
    engine and not for its support assistant, and the per-system answers
    travel on `system_ids` rather than being flattened away.
    """
    rule = _RULES.get((framework_key, reference_code))
    if rule is None:
        return RequirementApplicability(
            reference_code=reference_code,
            applies=True,
            reason="Applies to every organization that has adopted this framework.",
            status="applicable",
        )

    # Nothing declared. Every rule below reads facts, so answering them
    # from an all-false default would report "does not apply to you" for
    # a customer who has simply not been asked yet.
    if not profile.facts_declared:
        return RequirementApplicability(
            reference_code=reference_code,
            applies=True,
            reason=(
                "Whether this binds you depends on facts your organization has not "
                "declared yet. It is counted until you tell Veyntra otherwise."
            ),
            status="needs_review",
        )

    applies, reason = rule(profile)

    if not _is_system_dependent(framework_key, reference_code):
        return RequirementApplicability(
            reference_code=reference_code,
            applies=applies,
            reason=reason,
            status="applicable" if applies else "not_applicable",
        )

    binding = [
        system
        for system in profile.ai_systems
        if rule(profile.scoped_to(system))[0]
    ]

    if binding:
        names = ", ".join(system.name for system in binding)
        return RequirementApplicability(
            reference_code=reference_code,
            applies=True,
            reason=f"{reason} Applies to: {names}.",
            status="applicable",
            system_ids=[system.id for system in binding],
        )

    if applies:
        # The organization-level facts say yes but no registered system
        # confirms it — usually an inventory that is not complete yet.
        return RequirementApplicability(
            reference_code=reference_code,
            applies=True,
            reason=(
                f"{reason} No registered AI system matches this obligation yet, so it "
                "is counted but not confirmed — completing the inventory will settle it."
            ),
            status="likely_applicable",
        )

    return RequirementApplicability(
        reference_code=reference_code,
        applies=False,
        reason=reason,
        status="not_applicable",
    )


def evaluate_applicability_by_system(
    profile: OrganizationProfile, *, framework_key: str, reference_code: str
) -> dict[uuid.UUID, RequirementApplicability]:
    """The same question, answered once per registered AI system.

    `Organization -> AI System -> role -> risk class -> applicable`. An
    organization-level answer cannot express "Art. 72 binds the credit
    engine but not the support assistant", and adopting a framework must
    never apply a high-risk obligation to every system indiscriminately.
    """
    return {
        system.id: evaluate_applicability(
            profile.scoped_to(system),
            framework_key=framework_key,
            reference_code=reference_code,
        )
        for system in profile.ai_systems
    }


def applicable_codes(
    profile: OrganizationProfile, *, framework_key: str, reference_codes: list[str]
) -> set[str]:
    return {
        code
        for code in reference_codes
        if evaluate_applicability(
            profile, framework_key=framework_key, reference_code=code
        ).counts_toward_coverage
    }


__all__ = [
    "APPLICABILITY_STATUSES",
    "COUNTED_STATUSES",
    "HIGH_RISK_TIERS",
    "evaluate_applicability_by_system",
    "LIVE_DEPLOYMENT",
    "OrganizationProfile",
    "RequirementApplicability",
    "applicable_codes",
    "evaluate_applicability",
    "load_profile",
]
