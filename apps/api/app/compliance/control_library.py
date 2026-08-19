"""Common controls: one measure, many requirements.

The thing an organization actually does — "we restrict access to personal
data to authorised people" — satisfies GDPR Article 32, ISO 42001's
operational planning clause, and several others at once. Modelling that
as one control mapped to many requirements is the difference between a
compliance program and a filing system: adopt a second framework and most
of your existing evidence should already count, not need re-collecting
against a duplicate control with a different name.

The schema already supported this — `ControlMapping` is a composite-PK
join table — but the scaffolder did not use it, creating one control per
requirement. Adopting GDPR, the EU AI Act and ISO 42001 would have
produced 61 controls, most of them saying the same thing in three
different vocabularies, and asked the customer to evidence each one.

Each template below is a measure a growing software company would
recognise, with the requirements it genuinely supports. `satisfies` is
deliberately conservative: a control is listed against a requirement only
where holding that measure is real evidence toward it, not merely
adjacent to it. Over-claiming here inflates the readiness score, which is
the one number the whole product rests on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlTemplate:
    # Stable identifier used to recognise an existing control on
    # re-activation, so adopting a second framework extends the control
    # rather than duplicating it.
    key: str
    title: str
    description: str
    category: str
    priority: str
    # (framework_key, requirement_code) pairs this measure supports.
    satisfies: tuple[tuple[str, str], ...]


CONTROL_TEMPLATES: tuple[ControlTemplate, ...] = (
    ControlTemplate(
        key="privacy_notice",
        title="Publish and maintain a privacy notice",
        description=(
            "A privacy notice covering the identity of the controller, purposes, lawful "
            "bases, recipients, retention, transfers and data subject rights, kept current."
        ),
        category="Transparency",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 12"),
            ("gdpr", "Art. 13"),
            ("gdpr", "Art. 14"),
        ),
    ),
    ControlTemplate(
        key="lawful_basis_register",
        title="Record a lawful basis for every processing activity",
        description=(
            "Each processing activity has an identified and recorded lawful basis, with "
            "consent records where consent is relied on."
        ),
        category="Privacy",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 5"),
            ("gdpr", "Art. 6"),
            ("gdpr", "Art. 7"),
        ),
    ),
    ControlTemplate(
        key="ropa",
        title="Maintain records of processing activities",
        description=(
            "A record covering purposes, categories of data subjects and personal data, "
            "recipients, international transfers, retention periods and security measures."
        ),
        category="Privacy",
        priority="high",
        satisfies=(("gdpr", "Art. 30"),),
    ),
    ControlTemplate(
        key="data_subject_rights",
        title="Handle data subject requests within statutory timelines",
        description=(
            "A documented process for access, rectification, erasure, restriction, "
            "portability and objection requests, with identity verification and response "
            "inside one month."
        ),
        category="Privacy",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 15"),
            ("gdpr", "Art. 16"),
            ("gdpr", "Art. 17"),
            ("gdpr", "Art. 18"),
            ("gdpr", "Art. 20"),
            ("gdpr", "Art. 21"),
        ),
    ),
    ControlTemplate(
        key="access_control",
        title="Restrict access to personal data to authorised people",
        description=(
            "Role-based access control, least privilege, periodic access review, and "
            "authentication appropriate to the sensitivity of the data."
        ),
        category="Security",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 32"),
            ("gdpr", "Art. 25"),
            ("iso42001", "8.1"),
        ),
    ),
    ControlTemplate(
        key="security_of_processing",
        title="Apply technical and organisational security measures",
        description=(
            "Encryption in transit and at rest, resilience, backup and restore, and "
            "regular testing of the effectiveness of those measures."
        ),
        category="Security",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 32"),
            ("gdpr", "Art. 24"),
        ),
    ),
    ControlTemplate(
        key="breach_response",
        title="Detect, assess and notify personal data breaches",
        description=(
            "An incident response procedure that assesses breaches against the "
            "notification threshold, notifies the supervisory authority without undue "
            "delay and within 72 hours where feasible, and informs data subjects where "
            "the risk is high."
        ),
        category="Incident Response",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 33"),
            ("gdpr", "Art. 34"),
        ),
    ),
    ControlTemplate(
        key="dpia_process",
        title="Screen processing for DPIA and carry one out where required",
        description=(
            "A screening step against Article 35(3) and the EDPB criteria, and a DPIA "
            "covering the Article 35(7) content where high risk is indicated."
        ),
        category="Privacy",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 35"),
            ("iso42001", "8.4"),
        ),
    ),
    ControlTemplate(
        key="privacy_by_design",
        title="Build data protection into system design",
        description=(
            "Data minimisation, purpose limitation and default privacy settings "
            "considered at design time and recorded."
        ),
        category="Privacy",
        priority="medium",
        satisfies=(
            ("gdpr", "Art. 25"),
            ("gdpr", "Art. 5"),
        ),
    ),
    ControlTemplate(
        key="processor_agreements",
        title="Engage processors under a written data processing agreement",
        description=(
            "Article 28(3) terms in place with every processor, sub-processor "
            "authorisation controls, and a maintained list of sub-processors."
        ),
        category="Vendor Management",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 28"),
            ("gdpr", "Art. 26"),
            ("iso42001", "A.10.2"),
        ),
    ),
    ControlTemplate(
        key="international_transfers",
        title="Govern international transfers of personal data",
        description=(
            "Transfers rest on adequacy, appropriate safeguards such as SCCs, or a "
            "derogation, with transfer impact assessments where required."
        ),
        category="Privacy",
        priority="high",
        satisfies=(("gdpr", "Art. 44"),),
    ),
    ControlTemplate(
        key="special_category_data",
        title="Control processing of special category data",
        description=(
            "Special category data is identified, an Article 9(2) condition is recorded, "
            "and additional safeguards are applied."
        ),
        category="Privacy",
        priority="high",
        satisfies=(("gdpr", "Art. 9"),),
    ),
    ControlTemplate(
        key="automated_decisions",
        title="Govern automated decision-making and profiling",
        description=(
            "Solely automated decisions with legal or similarly significant effects are "
            "identified, given a lawful condition, and provided with human intervention "
            "and contest rights."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("gdpr", "Art. 22"),
            ("eu_ai_act", "Art. 14"),
        ),
    ),
    ControlTemplate(
        key="dpo_designation",
        title="Designate and publish a data protection contact",
        description=(
            "A DPO or equivalent privacy contact is designated where required, with "
            "published contact details and independence in the role."
        ),
        category="Governance",
        priority="medium",
        satisfies=(("gdpr", "Art. 37"),),
    ),
    # --- AI governance: spans the EU AI Act and ISO 42001 ---------------
    ControlTemplate(
        key="ai_system_inventory",
        title="Maintain an inventory of AI systems",
        description=(
            "Every AI system in use or development is recorded with its purpose, "
            "provider, model, data processed, affected users and deployment status."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("eu_ai_act", "Art. 6"),
            ("iso42001", "4.1"),
            ("iso42001", "8.1"),
        ),
    ),
    ControlTemplate(
        key="ai_risk_classification",
        title="Classify each AI system against the EU AI Act risk tiers",
        description=(
            "Each system is screened for prohibited practices and against the Annex I "
            "and Annex III high-risk criteria, with the reasoning recorded and reviewed "
            "by a person."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("eu_ai_act", "Art. 5"),
            ("eu_ai_act", "Art. 6"),
        ),
    ),
    ControlTemplate(
        key="ai_risk_management",
        title="Operate an AI risk management process",
        description=(
            "A continuous, iterative process identifying, evaluating and mitigating "
            "risks across the AI system lifecycle, with results retained."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("eu_ai_act", "Art. 9"),
            ("iso42001", "6.1"),
            ("iso42001", "8.2"),
            ("iso42001", "8.3"),
        ),
    ),
    ControlTemplate(
        key="ai_human_oversight",
        title="Provide effective human oversight of AI systems",
        description=(
            "Named people can interpret output, intervene and interrupt operation, with "
            "the oversight arrangement documented per system."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("eu_ai_act", "Art. 14"),
            ("eu_ai_act", "Art. 26"),
            ("iso42001", "A.9.2"),
        ),
    ),
    ControlTemplate(
        key="ai_transparency",
        title="Disclose AI interaction and generated content",
        description=(
            "People are informed when interacting with an AI system, and synthetic or "
            "manipulated content is marked as machine-generated."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("eu_ai_act", "Art. 50"),
            ("eu_ai_act", "Art. 13"),
        ),
    ),
    ControlTemplate(
        key="ai_data_governance",
        title="Govern data used to train, validate and test AI systems",
        description=(
            "Data sets are relevant and representative, examined for bias, and their "
            "provenance and governance practices are documented."
        ),
        category="AI Governance",
        priority="medium",
        satisfies=(
            ("eu_ai_act", "Art. 10"),
            ("iso42001", "8.1"),
        ),
    ),
    ControlTemplate(
        key="ai_technical_documentation",
        title="Maintain AI technical documentation and logs",
        description=(
            "Technical documentation is drawn up and kept current, and systems record "
            "events over their lifetime to support traceability."
        ),
        category="AI Governance",
        priority="medium",
        satisfies=(
            ("eu_ai_act", "Art. 11"),
            ("eu_ai_act", "Art. 12"),
            ("iso42001", "7.5"),
        ),
    ),
    ControlTemplate(
        key="ai_policy",
        title="Establish an AI policy and assign responsibility",
        description=(
            "A documented AI policy approved by leadership, with roles, "
            "responsibilities and authorities for AI governance assigned and communicated."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("iso42001", "5.2"),
            ("iso42001", "5.3"),
            ("eu_ai_act", "Art. 17"),
        ),
    ),
    ControlTemplate(
        key="ai_literacy",
        title="Ensure staff competence in AI use",
        description=(
            "People operating AI systems have a level of AI literacy appropriate to "
            "their role, evidenced by training records."
        ),
        category="AI Governance",
        priority="medium",
        satisfies=(
            ("eu_ai_act", "Art. 4"),
            ("iso42001", "7.2"),
        ),
    ),
    ControlTemplate(
        key="ai_monitoring",
        title="Monitor AI systems in production",
        description=(
            "Performance, accuracy and robustness are monitored after deployment, with "
            "a plan for collecting and reviewing operational data."
        ),
        category="AI Governance",
        priority="medium",
        satisfies=(
            ("eu_ai_act", "Art. 15"),
            ("eu_ai_act", "Art. 72"),
            ("iso42001", "9.1"),
        ),
    ),
    ControlTemplate(
        key="ai_impact_assessment",
        title="Assess the impact of AI systems on people",
        description=(
            "The effect of AI systems on individuals and groups, including fundamental "
            "rights, is assessed before deployment and retained."
        ),
        category="AI Governance",
        priority="high",
        satisfies=(
            ("eu_ai_act", "Art. 27"),
            ("iso42001", "8.4"),
        ),
    ),
    ControlTemplate(
        key="management_review",
        title="Review the compliance program at planned intervals",
        description=(
            "Leadership reviews objectives, performance, audit results and improvement "
            "actions at planned intervals, with the review recorded."
        ),
        category="Governance",
        priority="medium",
        satisfies=(
            ("iso42001", "9.2"),
            ("iso42001", "9.3"),
            ("iso42001", "10.1"),
            ("iso42001", "6.2"),
        ),
    ),
    ControlTemplate(
        key="interested_parties",
        title="Identify interested parties and their requirements",
        description=(
            "Customers, regulators, employees and partners with an interest in the AI "
            "management system are identified along with their requirements."
        ),
        category="Governance",
        priority="low",
        satisfies=(("iso42001", "4.2"),),
    ),
    ControlTemplate(
        key="gpai_obligations",
        title="Meet general-purpose AI model obligations",
        description=(
            "Where general-purpose AI models are provided, documentation, downstream "
            "information and a copyright policy are maintained."
        ),
        category="AI Governance",
        priority="low",
        satisfies=(
            ("eu_ai_act", "Art. 53"),
            ("eu_ai_act", "Art. 55"),
        ),
    ),
    ControlTemplate(
        key="ai_provider_obligations",
        title="Meet provider obligations for high-risk AI systems",
        description=(
            "Where the organization is a provider, conformity, corrective action and "
            "record-keeping obligations are met."
        ),
        category="AI Governance",
        priority="medium",
        satisfies=(("eu_ai_act", "Art. 16"),),
    ),
)

TEMPLATES_BY_KEY = {template.key: template for template in CONTROL_TEMPLATES}


def templates_for_framework(framework_key: str) -> list[ControlTemplate]:
    """Templates that satisfy at least one requirement of this framework."""
    return [
        template
        for template in CONTROL_TEMPLATES
        if any(fk == framework_key for fk, _ in template.satisfies)
    ]


__all__ = [
    "CONTROL_TEMPLATES",
    "TEMPLATES_BY_KEY",
    "ControlTemplate",
    "templates_for_framework",
]
