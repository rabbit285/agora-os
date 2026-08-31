"""The framework requirement catalog.

Everything downstream is measured against this. A readiness percentage,
a control mapping, a gap and a remediation task are all only as
meaningful as the requirement list they are computed from — a framework
carrying two requirements produces a score that looks precise and says
nothing.

GDPR, the EU AI Act and ISO/IEC 42001 carry real depth here because those
are the three the product commits to doing well. The remaining seeded
frameworks stay deliberately shallow: listing them lets an organization
adopt and track one, without implying a level of coverage that has not
been built.

`sensitivity="high"` marks requirements where a wrongly-accepted evidence
mapping is expensive to discover later. Evidence proposed against those
always reaches a human regardless of the model's confidence — see
`app.compliance.evidence_ai`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogRequirement:
    code: str
    title: str
    description: str
    sensitivity: str = "standard"


@dataclass(frozen=True)
class CatalogFramework:
    key: str
    name: str
    requirements: tuple[CatalogRequirement, ...]
    # False for the frameworks kept listed but not invested in. Surfaced
    # so the UI can be honest about depth rather than presenting a
    # two-requirement catalog as equivalent coverage.
    in_depth: bool = False


_GDPR = (
    CatalogRequirement(
        "Art. 5",
        "Principles relating to processing of personal data",
        "Lawfulness, fairness and transparency; purpose limitation; data minimisation; "
        "accuracy; storage limitation; integrity and confidentiality; and accountability.",
    ),
    CatalogRequirement(
        "Art. 6",
        "Lawfulness of processing",
        "Each processing activity rests on an identified lawful basis, recorded and "
        "capable of being demonstrated.",
    ),
    CatalogRequirement(
        "Art. 7",
        "Conditions for consent",
        "Where consent is the basis, it is freely given, specific, informed, "
        "unambiguous, demonstrable and as easy to withdraw as to give.",
    ),
    CatalogRequirement(
        "Art. 9",
        "Processing of special categories of personal data",
        "Special category data is processed only under an Article 9(2) condition, with "
        "the condition recorded.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 12",
        "Transparent information, communication and modalities",
        "Information and communications with data subjects are concise, transparent, "
        "intelligible and in plain language, with responses inside the statutory period.",
    ),
    CatalogRequirement(
        "Art. 13",
        "Information to be provided where data is collected from the data subject",
        "Identity of the controller, purposes, lawful basis, recipients, retention, "
        "transfers and data subject rights are disclosed at collection.",
    ),
    CatalogRequirement(
        "Art. 14",
        "Information to be provided where data has not been obtained from the data subject",
        "Equivalent disclosure where personal data is obtained from another source, "
        "including the categories of data and its origin.",
    ),
    CatalogRequirement(
        "Art. 15",
        "Right of access by the data subject",
        "Data subjects can obtain confirmation of processing, a copy of their data, and "
        "the accompanying information.",
    ),
    CatalogRequirement(
        "Art. 16",
        "Right to rectification",
        "Inaccurate personal data is corrected without undue delay, and incomplete data "
        "can be completed.",
    ),
    CatalogRequirement(
        "Art. 17",
        "Right to erasure",
        "Personal data is erased on request where one of the Article 17(1) grounds "
        "applies, including onward notification where it was made public.",
    ),
    CatalogRequirement(
        "Art. 18",
        "Right to restriction of processing",
        "Processing can be restricted rather than erased where the data subject "
        "contests accuracy or the processing is unlawful.",
    ),
    CatalogRequirement(
        "Art. 20",
        "Right to data portability",
        "Data provided by the subject is available in a structured, commonly used and "
        "machine-readable format.",
    ),
    CatalogRequirement(
        "Art. 21",
        "Right to object",
        "Data subjects can object to processing based on legitimate interests, and "
        "absolutely to direct marketing.",
    ),
    CatalogRequirement(
        "Art. 22",
        "Automated individual decision-making, including profiling",
        "Decisions producing legal or similarly significant effects are not made solely "
        "by automated means without a lawful condition and safeguards.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 24",
        "Responsibility of the controller",
        "Technical and organisational measures are implemented and reviewed to "
        "demonstrate that processing complies.",
    ),
    CatalogRequirement(
        "Art. 25",
        "Data protection by design and by default",
        "Data protection is built into processing design, and by default only data "
        "necessary for each purpose is processed.",
    ),
    CatalogRequirement(
        "Art. 26",
        "Joint controllers",
        "Where purposes and means are determined jointly, the respective "
        "responsibilities are set out in an arrangement.",
    ),
    CatalogRequirement(
        "Art. 28",
        "Processor",
        "Processors are engaged under a written contract meeting Article 28(3), with "
        "sufficient guarantees and controls over sub-processors.",
    ),
    CatalogRequirement(
        "Art. 30",
        "Records of processing activities",
        "A record is maintained covering purposes, categories of data subjects and "
        "data, recipients, transfers, retention periods and security measures.",
    ),
    CatalogRequirement(
        "Art. 32",
        "Security of processing",
        "Technical and organisational measures appropriate to the risk, including "
        "pseudonymisation, encryption, resilience and regular testing.",
    ),
    CatalogRequirement(
        "Art. 33",
        "Notification of a personal data breach to the supervisory authority",
        "Notifiable breaches are reported without undue delay and, where feasible, "
        "within 72 hours of becoming aware.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 34",
        "Communication of a personal data breach to the data subject",
        "Where a breach is likely to result in high risk, affected data subjects are "
        "informed without undue delay.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 35",
        "Data protection impact assessment",
        "A DPIA is carried out where processing is likely to result in a high risk, "
        "covering the assessment content required by Article 35(7).",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 37",
        "Designation of the data protection officer",
        "A DPO is designated where required, with published contact details and "
        "independence in performing the role.",
    ),
    CatalogRequirement(
        "Art. 44",
        "General principle for transfers of personal data",
        "Transfers to third countries take place only under an adequacy decision, "
        "appropriate safeguards, or a derogation.",
        sensitivity="high",
    ),
)


_EU_AI_ACT = (
    CatalogRequirement(
        "Art. 4",
        "AI literacy",
        "Staff and others operating AI systems on the organization's behalf have a "
        "sufficient level of AI literacy for their role and context.",
    ),
    CatalogRequirement(
        "Art. 5",
        "Prohibited AI practices",
        "No AI system is placed on the market or used for a practice prohibited under "
        "Article 5.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 6",
        "Classification rules for high-risk AI systems",
        "Each AI system is classified against the Annex I and Annex III criteria, and "
        "the classification is recorded with its reasoning.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 9",
        "Risk management system",
        "A continuous, iterative risk management process runs across the lifecycle of "
        "each high-risk AI system.",
    ),
    CatalogRequirement(
        "Art. 10",
        "Data and data governance",
        "Training, validation and testing data sets are relevant, representative, and "
        "examined for bias, with governance practices documented.",
    ),
    CatalogRequirement(
        "Art. 11",
        "Technical documentation",
        "Technical documentation is drawn up before placing on the market and kept "
        "up to date, covering the Annex IV content.",
    ),
    CatalogRequirement(
        "Art. 12",
        "Record-keeping",
        "High-risk AI systems technically allow for the automatic recording of events "
        "over their lifetime.",
    ),
    CatalogRequirement(
        "Art. 13",
        "Transparency and provision of information to deployers",
        "Operation is sufficiently transparent for deployers to interpret output and "
        "use the system appropriately, with instructions for use.",
    ),
    CatalogRequirement(
        "Art. 14",
        "Human oversight",
        "High-risk AI systems are designed so they can be effectively overseen by "
        "natural persons, including the ability to intervene or interrupt.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 15",
        "Accuracy, robustness and cybersecurity",
        "Systems achieve an appropriate level of accuracy, robustness and "
        "cybersecurity, and perform consistently across their lifecycle.",
    ),
    CatalogRequirement(
        "Art. 16",
        "Obligations of providers of high-risk AI systems",
        "Providers ensure conformity, maintain a quality management system, keep "
        "documentation and logs, and take corrective action.",
    ),
    CatalogRequirement(
        "Art. 17",
        "Quality management system",
        "Providers of high-risk AI systems operate a documented quality management "
        "system covering the Article 17 elements.",
    ),
    CatalogRequirement(
        "Art. 26",
        "Obligations of deployers of high-risk AI systems",
        "Deployers use systems per the instructions, assign competent human oversight, "
        "monitor operation and retain logs.",
    ),
    CatalogRequirement(
        "Art. 27",
        "Fundamental rights impact assessment",
        "Certain deployers assess the impact on fundamental rights before putting a "
        "high-risk AI system into use.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "Art. 50",
        "Transparency obligations for providers and deployers of certain AI systems",
        "People are informed when interacting with an AI system, and synthetic or "
        "manipulated content is marked as such.",
    ),
    CatalogRequirement(
        "Art. 53",
        "Obligations for providers of general-purpose AI models",
        "Providers of GPAI models maintain technical documentation, information for "
        "downstream providers, and a copyright policy.",
    ),
    CatalogRequirement(
        "Art. 55",
        "Obligations for providers of general-purpose AI models with systemic risk",
        "Model evaluation, systemic risk assessment and mitigation, incident tracking "
        "and cybersecurity protection.",
    ),
    CatalogRequirement(
        "Art. 72",
        "Post-market monitoring by providers of high-risk AI systems",
        "A post-market monitoring plan collects and reviews performance data across "
        "the lifetime of the system.",
    ),
)


_ISO_42001 = (
    CatalogRequirement(
        "4.1",
        "Understanding the organization and its context",
        "External and internal issues relevant to the AI management system, and the "
        "organization's role across the AI lifecycle, are determined.",
    ),
    CatalogRequirement(
        "4.2",
        "Understanding the needs and expectations of interested parties",
        "Interested parties and their relevant requirements for the AI management "
        "system are identified.",
    ),
    CatalogRequirement(
        "5.2",
        "AI policy",
        "Top management establishes an AI policy appropriate to the organization's "
        "purpose, communicated and available as documented information.",
    ),
    CatalogRequirement(
        "5.3",
        "Roles, responsibilities and authorities",
        "Responsibilities and authorities for the AI management system are assigned "
        "and communicated.",
    ),
    CatalogRequirement(
        "6.1",
        "Actions to address risks and opportunities",
        "Risks and opportunities for the AI management system are determined and "
        "planned for, including AI risk assessment and treatment.",
    ),
    CatalogRequirement(
        "6.2",
        "AI objectives and planning to achieve them",
        "Measurable AI objectives are established at relevant functions and levels, "
        "with plans to achieve them.",
    ),
    CatalogRequirement(
        "7.2",
        "Competence",
        "Persons doing work affecting AI performance are competent on the basis of "
        "education, training or experience.",
    ),
    CatalogRequirement(
        "7.5",
        "Documented information",
        "The AI management system includes the documented information required by the "
        "standard and that determined as necessary.",
    ),
    CatalogRequirement(
        "8.1",
        "Operational planning and control",
        "Processes needed to meet AI management system requirements are planned, "
        "implemented and controlled.",
    ),
    CatalogRequirement(
        "8.2",
        "AI risk assessment",
        "AI risk assessments are performed at planned intervals and when significant "
        "changes occur, with results retained.",
    ),
    CatalogRequirement(
        "8.3",
        "AI risk treatment",
        "The AI risk treatment plan is implemented and its results retained as "
        "documented information.",
    ),
    CatalogRequirement(
        "8.4",
        "AI system impact assessment",
        "The impact of AI systems on individuals and groups is assessed across the "
        "lifecycle, and results retained.",
        sensitivity="high",
    ),
    CatalogRequirement(
        "9.1",
        "Monitoring, measurement, analysis and evaluation",
        "What needs monitoring, the methods, and when results are analysed and "
        "evaluated, are determined and carried out.",
    ),
    CatalogRequirement(
        "9.2",
        "Internal audit",
        "Internal audits are conducted at planned intervals to confirm the AI "
        "management system conforms and is effectively implemented.",
    ),
    CatalogRequirement(
        "9.3",
        "Management review",
        "Top management reviews the AI management system at planned intervals for "
        "continuing suitability, adequacy and effectiveness.",
    ),
    CatalogRequirement(
        "10.1",
        "Continual improvement and nonconformity",
        "Nonconformities are reacted to and corrected, and the AI management system is "
        "continually improved.",
    ),
    CatalogRequirement(
        "A.9.2",
        "Responsible use of AI systems",
        "Objectives and processes for the responsible use of AI systems are defined "
        "and applied.",
    ),
    CatalogRequirement(
        "A.10.2",
        "Third-party relationships in the AI system lifecycle",
        "Responsibilities are allocated and risks managed where suppliers or partners "
        "participate in the AI system lifecycle.",
    ),
)


# Kept listed so an organization can adopt and track one, without
# implying coverage that has not been built. `in_depth=False` is what the
# UI reads to say so honestly.
_SHALLOW = {
    "iso27001": (
        "ISO 27001",
        (
            CatalogRequirement(
                "A.5.1", "Policies for information security", "Information security policy set."
            ),
            CatalogRequirement(
                "A.8.1",
                "Inventory of information and other associated assets",
                "An inventory of assets associated with information is maintained.",
            ),
        ),
    ),
    "soc2": (
        "SOC 2",
        (
            CatalogRequirement(
                "CC6.1",
                "Logical and physical access controls",
                "Access to systems and data is restricted to authorised users.",
            ),
            CatalogRequirement(
                "CC7.2",
                "System monitoring to detect security events",
                "Systems are monitored to detect and respond to security events.",
            ),
        ),
    ),
    "nis2": (
        "NIS2",
        (
            CatalogRequirement(
                "Art. 21",
                "Cybersecurity risk-management measures",
                "Appropriate and proportionate technical and organisational measures.",
            ),
            CatalogRequirement(
                "Art. 23",
                "Reporting obligations",
                "Significant incidents are reported within the directive's timelines.",
                sensitivity="high",
            ),
        ),
    ),
    "dora": (
        "DORA",
        (
            CatalogRequirement(
                "Art. 5",
                "ICT risk management framework",
                "A sound, comprehensive and well-documented ICT risk management framework.",
            ),
            CatalogRequirement(
                "Art. 28",
                "General principles for ICT third-party risk",
                "ICT third-party risk is managed as an integral part of ICT risk management.",
            ),
        ),
    ),
}


CATALOG: tuple[CatalogFramework, ...] = (
    CatalogFramework("gdpr", "GDPR", _GDPR, in_depth=True),
    CatalogFramework("eu_ai_act", "EU AI Act", _EU_AI_ACT, in_depth=True),
    CatalogFramework("iso42001", "ISO 42001", _ISO_42001, in_depth=True),
    *(
        CatalogFramework(key, name, requirements)
        for key, (name, requirements) in _SHALLOW.items()
    ),
)

CATALOG_BY_KEY = {framework.key: framework for framework in CATALOG}

# The three the product commits to doing well.
PRIORITY_FRAMEWORK_KEYS = tuple(f.key for f in CATALOG if f.in_depth)


__all__ = [
    "CATALOG",
    "CATALOG_BY_KEY",
    "PRIORITY_FRAMEWORK_KEYS",
    "CatalogFramework",
    "CatalogRequirement",
]
