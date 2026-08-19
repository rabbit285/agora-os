"""Which frameworks does this organization actually have to satisfy?

The customer this exists for is a 60-person software company whose
enterprise buyers have started asking "are you GDPR compliant" and "how
do you govern AI". They do not have a compliance department, and the
question they cannot answer on their own is not "how do I evidence ISO
27001" — it is "which of these six things even applies to me".

**Rules over declared facts, never a model call.** Applicability is a
legal question with a mostly mechanical answer: GDPR applies because you
process personal data of people in the EU, not because a model felt it
did. Every recommendation here is computed from facts the organization
declared about itself, and each one carries the specific facts that
produced it. That makes the output arguable — a customer can look at a
recommendation, disagree with the fact behind it, change the fact, and
get a different answer. A generated paragraph cannot be argued with.

**Applicability is not compliance.** This says a framework is in scope.
It says nothing about whether the organization meets it — that is what
the assessment does, from evidence.

**Where the answer is genuinely uncertain, say so.** NIS2 sector scope
and DORA's definition of a financial entity turn on details this product
does not hold and should not guess at. Those come back flagged for legal
review rather than asserted, because telling a company they are out of
scope of NIS2 when they are not is the most expensive thing this module
could do.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ordered strongest to weakest. "required" means the declared facts put
# the organization squarely in scope; "likely" means in scope on the
# facts we hold but turning on a definition we do not; "recommended"
# means not legally mandated but commercially expected.
APPLICABILITY_LEVELS = ("required", "likely", "recommended", "not_indicated")

# Sectors NIS2 names as essential or important entities. Deliberately
# coarse: the directive's own annexes are finer than anything a signup
# form can capture, which is exactly why a match here produces "likely"
# plus a legal-review flag rather than "required".
NIS2_SECTORS = frozenset(
    {
        "critical_infrastructure",
        "energy",
        "transport",
        "health",
        "digital_infrastructure",
        "public_administration",
        "managed_services",
    }
)

FINANCIAL_SECTORS = frozenset({"financial", "insurance", "payments"})


@dataclass
class CompanyFacts:
    """What the organization has declared about itself.

    Every field defaults to the answer that keeps a framework *out* of
    scope. An unanswered question must never manufacture an obligation —
    a recommendation the customer cannot trace to something they said is
    indistinguishable from a guess.
    """

    operates_in_eu: bool = False
    sells_to_eu_customers: bool = False
    processes_personal_data: bool = False
    processes_special_category_data: bool = False
    uses_third_party_ai: bool = False
    builds_ai_features: bool = False
    is_data_processor: bool = False
    sells_to_enterprise: bool = False
    sector: str | None = None
    employee_count_range: str | None = None

    @property
    def has_eu_nexus(self) -> bool:
        return self.operates_in_eu or self.sells_to_eu_customers

    @property
    def touches_ai(self) -> bool:
        return self.uses_third_party_ai or self.builds_ai_features


@dataclass
class FrameworkRecommendation:
    framework_key: str
    applicability: str
    # The declared facts that produced this, in the organization's own
    # terms. Shown in the UI so a recommendation can be argued with.
    reasons: list[str] = field(default_factory=list)
    # Where our answer turns on something we do not hold.
    uncertainties: list[str] = field(default_factory=list)
    requires_legal_review: bool = False


def _employees_at_least_50(employee_count_range: str | None) -> bool:
    """NIS2's size threshold, read off the signup form's coarse bands.

    Returns False for an unset or unrecognized band: an unknown headcount
    must not put a company in scope of a directive by default.
    """
    return employee_count_range in {"51-200", "201-1000", "1000+"}


def _gdpr(facts: CompanyFacts) -> FrameworkRecommendation:
    reasons: list[str] = []
    if facts.processes_personal_data and facts.has_eu_nexus:
        if facts.operates_in_eu:
            reasons.append("You operate in the European Union.")
        if facts.sells_to_eu_customers:
            reasons.append("You sell to customers in the European Union.")
        reasons.append("You process personal data.")
        if facts.processes_special_category_data:
            reasons.append(
                "You process special category data, which carries additional "
                "conditions under Article 9."
            )
        if facts.is_data_processor:
            reasons.append(
                "You process personal data on behalf of your customers, so Article 28 "
                "processor obligations and a DPA apply."
            )
        return FrameworkRecommendation(
            framework_key="gdpr", applicability="required", reasons=reasons
        )

    if facts.processes_personal_data:
        return FrameworkRecommendation(
            framework_key="gdpr",
            applicability="recommended",
            reasons=["You process personal data, but declared no EU operations or customers."],
            uncertainties=[
                "GDPR can still apply through the establishment or targeting tests in "
                "Article 3 even without an EU entity."
            ],
            requires_legal_review=True,
        )

    return FrameworkRecommendation(framework_key="gdpr", applicability="not_indicated")


def _eu_ai_act(facts: CompanyFacts) -> FrameworkRecommendation:
    if not facts.touches_ai:
        return FrameworkRecommendation(framework_key="eu_ai_act", applicability="not_indicated")

    if not facts.has_eu_nexus:
        return FrameworkRecommendation(
            framework_key="eu_ai_act",
            applicability="recommended",
            reasons=["You use or build AI systems, but declared no EU operations or customers."],
            uncertainties=[
                "The Act reaches providers and deployers outside the EU where the output "
                "is used in the Union."
            ],
            requires_legal_review=True,
        )

    reasons: list[str] = []
    if facts.builds_ai_features:
        reasons.append(
            "You build AI features into your product, which can make you a provider "
            "under the Act."
        )
    if facts.uses_third_party_ai:
        reasons.append(
            "You use third-party AI systems, which makes you a deployer under the Act."
        )
    reasons.append("Your AI systems reach the European Union.")

    return FrameworkRecommendation(
        framework_key="eu_ai_act",
        applicability="required",
        reasons=reasons,
        uncertainties=[
            "Which obligations apply depends on the risk classification of each system. "
            "Screen them individually under AI Governance."
        ],
    )


def _iso_42001(facts: CompanyFacts) -> FrameworkRecommendation:
    if facts.builds_ai_features:
        reasons = ["You build AI features, so an AI management system is the standard way to govern them."]
        if facts.sells_to_enterprise:
            reasons.append("Enterprise buyers increasingly ask for it alongside ISO 27001.")
        return FrameworkRecommendation(
            framework_key="iso42001", applicability="recommended", reasons=reasons
        )
    if facts.uses_third_party_ai and facts.sells_to_enterprise:
        return FrameworkRecommendation(
            framework_key="iso42001",
            applicability="recommended",
            reasons=[
                "You use AI systems and sell to enterprise customers, who increasingly ask "
                "how AI is governed."
            ],
        )
    return FrameworkRecommendation(framework_key="iso42001", applicability="not_indicated")


def _iso_27001(facts: CompanyFacts) -> FrameworkRecommendation:
    reasons: list[str] = []
    if facts.sells_to_enterprise:
        reasons.append(
            "You sell to enterprise customers, who commonly require a recognised security "
            "certification before signing."
        )
    if facts.is_data_processor:
        reasons.append(
            "You process data on behalf of customers, so your security posture is part of "
            "their due diligence."
        )
    if reasons:
        return FrameworkRecommendation(
            framework_key="iso27001", applicability="recommended", reasons=reasons
        )
    return FrameworkRecommendation(framework_key="iso27001", applicability="not_indicated")


def _soc2(facts: CompanyFacts) -> FrameworkRecommendation:
    if facts.sells_to_enterprise:
        return FrameworkRecommendation(
            framework_key="soc2",
            applicability="recommended",
            reasons=[
                "You sell to enterprise customers. SOC 2 is the assurance report North "
                "American buyers ask for most often."
            ],
            uncertainties=[
                "SOC 2 and ISO 27001 cover much of the same ground. Most companies this "
                "size pick one to start."
            ],
        )
    return FrameworkRecommendation(framework_key="soc2", applicability="not_indicated")


def _nis2(facts: CompanyFacts) -> FrameworkRecommendation:
    """Deliberately never returns "required".

    NIS2 scope turns on sector annexes and entity size thresholds that a
    company profile cannot settle. Telling a company they are out of scope
    when they are not is the most expensive mistake available here, so an
    indication produces "likely" plus a legal-review flag, and everything
    else stays quiet rather than asserting an exemption.
    """
    if facts.sector in NIS2_SECTORS and facts.has_eu_nexus:
        reasons = [f"You operate in the {facts.sector.replace('_', ' ')} sector within the EU."]
        if _employees_at_least_50(facts.employee_count_range):
            reasons.append("You are above the size threshold NIS2 generally applies from.")
        return FrameworkRecommendation(
            framework_key="nis2",
            applicability="likely",
            reasons=reasons,
            uncertainties=[
                "NIS2 scope depends on the sector annexes and national implementation. "
                "Confirm with counsel before treating this as settled."
            ],
            requires_legal_review=True,
        )
    return FrameworkRecommendation(framework_key="nis2", applicability="not_indicated")


def _dora(facts: CompanyFacts) -> FrameworkRecommendation:
    if facts.sector in FINANCIAL_SECTORS and facts.has_eu_nexus:
        return FrameworkRecommendation(
            framework_key="dora",
            applicability="likely",
            reasons=["You operate in the financial sector within the EU."],
            uncertainties=[
                "DORA applies to defined financial entities and their critical ICT "
                "providers. Confirm which category you fall into with counsel."
            ],
            requires_legal_review=True,
        )
    if facts.is_data_processor and facts.sector in FINANCIAL_SECTORS:
        return FrameworkRecommendation(
            framework_key="dora",
            applicability="likely",
            reasons=["You provide ICT services to financial sector customers."],
            uncertainties=["Critical ICT third-party provider designation is made by regulators."],
            requires_legal_review=True,
        )
    return FrameworkRecommendation(framework_key="dora", applicability="not_indicated")


_RULES = (_gdpr, _eu_ai_act, _iso_42001, _iso_27001, _soc2, _nis2, _dora)


def recommend_frameworks(facts: CompanyFacts) -> list[FrameworkRecommendation]:
    """Every framework we hold an opinion on, strongest first.

    Frameworks with no indication are returned too, with
    `not_indicated` and no reasons. Showing them is deliberate: a
    customer needs to see that NIS2 was considered and found not to apply,
    rather than wonder whether it was simply forgotten.
    """
    recommendations = [rule(facts) for rule in _RULES]
    return sorted(
        recommendations,
        key=lambda r: (APPLICABILITY_LEVELS.index(r.applicability), r.framework_key),
    )


def applicable_framework_keys(facts: CompanyFacts) -> list[str]:
    """Just the keys worth adopting — everything not `not_indicated`."""
    return [
        r.framework_key
        for r in recommend_frameworks(facts)
        if r.applicability != "not_indicated"
    ]


__all__ = [
    "APPLICABILITY_LEVELS",
    "CompanyFacts",
    "FrameworkRecommendation",
    "applicable_framework_keys",
    "recommend_frameworks",
]
