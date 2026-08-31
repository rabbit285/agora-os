"""Turning a gap into work somebody can actually pick up.

A finding that says "attach the documents that demonstrate this control"
is not remediation. It restates the gap, tells the reader nothing they
did not know, and leaves them to work out what a complete answer looks
like — which is the expertise they came here to buy.

A plan here therefore carries: the specific deficiency, why it exists,
what evidence was already looked at, what is missing, who usually owns
this kind of work, what evidence would close it, and an ordered checklist
of steps. The checklist is the part that matters most: it converts "you
are missing AI literacy training" into six things a person can do this
week.

**Assembled, not generated.** Playbooks are written against the
regulation's own requirements. A model asked to invent remediation for a
legal obligation will produce something plausible and occasionally wrong,
and wrong here means a company does work that does not close the gap. The
generic fallback is deliberately modest for the same reason: where there
is no playbook it says what it can from the requirement text and asks for
the evidence, rather than inventing steps it cannot stand behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Teams as a growing software company actually has them. Used as a
# suggestion the customer can override, never an assignment — we do not
# know their org chart.
OWNER_ENGINEERING = "Engineering"
OWNER_SECURITY = "Security"
OWNER_LEGAL = "Legal / Privacy"
OWNER_HR = "HR / People"
OWNER_IT = "IT"
OWNER_MANAGEMENT = "Management"
OWNER_COMPLIANCE = "Compliance"


# The five kinds document intelligence labels a passage with. Closed
# set, and the same list the model is given — see the `evidence_type`
# field in app.compliance.evidence_ai. Tagging expectations with these
# is what lets the product say *which* condition is unmet instead of
# asking the customer to work it out.
TYPE_POLICY = "policy_statement"
TYPE_PROCEDURE = "procedure"
TYPE_RECORD = "record"
TYPE_ATTESTATION = "attestation"


@dataclass(frozen=True)
class ExpectedEvidence:
    """One thing a complete answer to a requirement contains.

    `satisfied_by` names the evidence types that would demonstrate it.
    An empty tuple means this item cannot be checked mechanically, and
    its absence is therefore never reported as a confirmed deficiency —
    the requirement is held at `needs_review` instead. Saying "you are
    missing X" when we cannot actually tell is the failure mode that
    teaches people to stop reading findings.
    """

    description: str
    satisfied_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    """What a complete answer to one requirement looks like."""

    problem: str
    action: str
    owner: str
    required_evidence: tuple[ExpectedEvidence, ...]
    checklist: tuple[str, ...]
    # Days from now. Reflects how long the work realistically takes, not
    # a uniform SLA — writing a policy is not the same job as running a
    # training programme.
    due_in_days: int = 30


@dataclass
class RemediationPlan:
    """The full plan, as the task and the gap detail both render it."""

    problem: str
    why: str
    action: str
    owner: str
    priority: str
    due_in_days: int
    required_evidence: list[str] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)
    evidence_reviewed: list[str] = field(default_factory=list)
    # The specific conditions the evidence on file does not meet, named
    # by the coverage analysis rather than left for the customer to work
    # out. Empty when the deficiency is simply "nothing on file".
    missing_conditions: list[str] = field(default_factory=list)
    missing_evidence: str = ""
    requirement_code: str = ""
    requirement_title: str = ""
    framework_name: str = ""
    control_title: str | None = None
    affected_ai_systems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "problem": self.problem,
            "why": self.why,
            "action": self.action,
            "owner": self.owner,
            "priority": self.priority,
            "due_in_days": self.due_in_days,
            "required_evidence": self.required_evidence,
            "checklist": self.checklist,
            "evidence_reviewed": self.evidence_reviewed,
            "missing_conditions": self.missing_conditions,
            "missing_evidence": self.missing_evidence,
            "requirement_code": self.requirement_code,
            "requirement_title": self.requirement_title,
            "framework_name": self.framework_name,
            "control_title": self.control_title,
            "affected_ai_systems": self.affected_ai_systems,
        }


PLAYBOOKS: dict[tuple[str, str], Playbook] = {
    # --- EU AI Act ----------------------------------------------------
    ("eu_ai_act", "Art. 4"): Playbook(
        problem=(
            "AI literacy expectations may be documented, but no evidence of completed AI "
            "literacy training for the people who operate or oversee AI systems was found."
        ),
        action=(
            "Establish and deliver an AI literacy programme proportionate to each role's "
            "involvement with AI, and keep records of who completed it."
        ),
        owner=OWNER_HR,
        required_evidence=(
            ExpectedEvidence(
                "AI literacy training policy or programme outline",
                (TYPE_POLICY,),
            ),
            ExpectedEvidence(
                "The training materials themselves",
                (TYPE_PROCEDURE,),
            ),
            ExpectedEvidence(
                "Attendance or completion records naming the people trained",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "Employee acknowledgements",
                (TYPE_RECORD, TYPE_ATTESTATION),
            ),
        ),
        checklist=(
            "Identify everyone who uses or oversees an AI system",
            "Define the literacy topics each role needs",
            "Approve the training materials",
            "Deliver the training",
            "Record completion per person",
            "Upload the records as evidence",
        ),
        due_in_days=45,
    ),
    ("eu_ai_act", "Art. 5"): Playbook(
        problem=(
            "No record was found showing that AI systems have been checked against the "
            "prohibited practices in Article 5."
        ),
        action=(
            "Screen every AI system against the prohibited practices and record the outcome "
            "with the reasoning behind it."
        ),
        owner=OWNER_LEGAL,
        required_evidence=(
            ExpectedEvidence(
                "A screening record per AI system against each prohibited practice",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "Sign-off from whoever is accountable for the conclusion",
                (TYPE_ATTESTATION,),
            ),
        ),
        checklist=(
            "List every AI system in the inventory",
            "Assess each against the Article 5 prohibited practices",
            "Record the conclusion and the reasoning",
            "Have the conclusions reviewed",
            "Upload the screening records as evidence",
        ),
        due_in_days=30,
    ),
    ("eu_ai_act", "Art. 6"): Playbook(
        problem=(
            "AI systems are recorded but their risk classification has not been established "
            "from their actual purpose and use."
        ),
        action=(
            "Classify each AI system against the Annex I and Annex III criteria and record "
            "the basis for the classification."
        ),
        owner=OWNER_COMPLIANCE,
        required_evidence=(
            ExpectedEvidence(
                "A classification record per AI system",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "The reasoning and the criteria applied",
                (TYPE_POLICY, TYPE_PROCEDURE),
            ),
        ),
        checklist=(
            "Review each AI system's purpose and deployment context",
            "Apply the Annex I and Annex III criteria",
            "Record the tier and the reasoning",
            "Have a person confirm each classification",
            "Upload the classification records",
        ),
        due_in_days=30,
    ),
    ("eu_ai_act", "Art. 14"): Playbook(
        problem=(
            "No evidence was found describing how a person can interpret, intervene in, or "
            "interrupt the operation of the AI systems that need oversight."
        ),
        action=(
            "Document the human oversight arrangement for each system: who watches it, what "
            "they can see, and how they stop or override it."
        ),
        owner=OWNER_ENGINEERING,
        required_evidence=(
            ExpectedEvidence(
                "A human oversight procedure per system",
                (TYPE_PROCEDURE,),
            ),
            ExpectedEvidence(
                "The escalation and override path",
                (TYPE_PROCEDURE,),
            ),
            ExpectedEvidence(
                "Named people holding the oversight role",
                (TYPE_RECORD,),
            ),
        ),
        checklist=(
            "Name the person or role overseeing each system",
            "Describe what they can observe about its output",
            "Define how they intervene, override or stop it",
            "Test the override path works",
            "Upload the procedure as evidence",
        ),
        due_in_days=30,
    ),
    ("eu_ai_act", "Art. 50"): Playbook(
        problem=(
            "No evidence was found that people are told when they are interacting with an AI "
            "system, or that machine-generated content is marked as such."
        ),
        action=(
            "Add and evidence a disclosure wherever a person interacts with an AI system or "
            "receives content it generated."
        ),
        owner=OWNER_ENGINEERING,
        required_evidence=(
            ExpectedEvidence(
                "Screenshots or copy showing the disclosure in the product",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "The content-marking approach for generated output",
                (TYPE_POLICY, TYPE_PROCEDURE),
            ),
        ),
        checklist=(
            "Find every place a person meets an AI system",
            "Write the disclosure wording",
            "Ship the disclosure",
            "Mark machine-generated content",
            "Capture evidence of both",
        ),
        due_in_days=21,
    ),
    # --- GDPR ----------------------------------------------------------
    ("gdpr", "Art. 30"): Playbook(
        problem=(
            "No Record of Processing Activities covering the Article 30(1) fields was found."
        ),
        action=(
            "Prepare and approve a Record of Processing Activities covering purposes, "
            "categories of data subjects and personal data, recipients, transfers, retention "
            "periods and security measures."
        ),
        owner=OWNER_LEGAL,
        required_evidence=(
            ExpectedEvidence(
                "The completed Record of Processing Activities",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "Evidence of approval and its review date",
                (TYPE_RECORD, TYPE_ATTESTATION),
            ),
        ),
        checklist=(
            "List every processing activity across the business",
            "For each, record purpose, data categories and data subjects",
            "Record recipients and any international transfers",
            "Record retention periods and security measures",
            "Have the record approved",
            "Upload it as evidence",
        ),
        due_in_days=30,
    ),
    ("gdpr", "Art. 33"): Playbook(
        problem=(
            "No breach procedure was found showing how a personal data breach is assessed "
            "against the 72-hour notification threshold."
        ),
        action=(
            "Document a personal data breach procedure covering detection, assessment, "
            "notification and the internal breach register."
        ),
        owner=OWNER_SECURITY,
        required_evidence=(
            ExpectedEvidence(
                "The breach response procedure",
                (TYPE_PROCEDURE,),
            ),
            ExpectedEvidence(
                "The internal breach register",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "Evidence the procedure has been exercised or tested",
                (TYPE_RECORD,),
            ),
        ),
        checklist=(
            "Define how a suspected breach is detected and raised",
            "Define who assesses it against the notification threshold",
            "Write the supervisory-authority notification path and timing",
            "Define when data subjects are told directly",
            "Set up the internal breach register",
            "Run a tabletop exercise and record it",
            "Upload the procedure and the exercise record",
        ),
        due_in_days=30,
    ),
    ("gdpr", "Art. 35"): Playbook(
        problem=(
            "No DPIA screening procedure or completed DPIA was found for processing likely "
            "to result in a high risk."
        ),
        action=(
            "Document how processing is screened for DPIA triggers and complete a DPIA where "
            "the screening indicates one is required."
        ),
        owner=OWNER_LEGAL,
        required_evidence=(
            ExpectedEvidence(
                "The DPIA screening procedure",
                (TYPE_PROCEDURE,),
            ),
            ExpectedEvidence(
                "At least one completed DPIA covering the Article 35(7) content",
                (TYPE_RECORD,),
            ),
            ExpectedEvidence(
                "Evidence of DPO consultation where one is appointed",
                (TYPE_RECORD,),
            ),
        ),
        checklist=(
            "Write the screening criteria based on Article 35(3) and the EDPB list",
            "Screen current processing activities",
            "Complete a DPIA for anything the screening flags",
            "Record residual risk and the mitigations",
            "Obtain sign-off",
            "Upload the screening procedure and the DPIA",
        ),
        due_in_days=45,
    ),
    ("gdpr", "Art. 32"): Playbook(
        problem=(
            "No evidence was found of the technical and organisational measures protecting "
            "personal data, or of them being tested."
        ),
        action=(
            "Document the security measures in place and evidence that their effectiveness "
            "is tested regularly."
        ),
        owner=OWNER_SECURITY,
        required_evidence=(
            ExpectedEvidence(
                "The information security policy",
                (TYPE_POLICY,),
            ),
            ExpectedEvidence(
                "Encryption and access control configuration evidence",
                (TYPE_RECORD, TYPE_PROCEDURE),
            ),
            ExpectedEvidence(
                "Backup restoration test results",
                (TYPE_RECORD,),
            ),
        ),
        checklist=(
            "Document encryption in transit and at rest",
            "Document access control and review cadence",
            "Document backup and restoration",
            "Run a restoration test and record the result",
            "Upload the policy and the test evidence",
        ),
        due_in_days=30,
    ),
    # --- ISO 42001 -----------------------------------------------------
    ("iso42001", "7.2"): Playbook(
        problem=(
            "No competence records were found for the people whose work affects AI "
            "performance."
        ),
        action=(
            "Define the competence each AI-affecting role needs and keep records showing "
            "people meet it."
        ),
        owner=OWNER_HR,
        required_evidence=(
            ExpectedEvidence(
                "Role competence definitions",
                (TYPE_POLICY,),
            ),
            ExpectedEvidence(
                "Training or qualification records per person",
                (TYPE_RECORD,),
            ),
        ),
        checklist=(
            "List the roles whose work affects AI outcomes",
            "Define the competence each needs",
            "Assess current staff against it",
            "Close any gaps with training",
            "Upload the records",
        ),
        due_in_days=45,
    ),
    ("iso42001", "5.2"): Playbook(
        problem="No approved AI policy was found.",
        action=(
            "Write an AI policy appropriate to the organization's purpose, have leadership "
            "approve it, and communicate it."
        ),
        owner=OWNER_MANAGEMENT,
        required_evidence=(
            ExpectedEvidence(
                "The approved AI policy",
                (TYPE_POLICY,),
            ),
            ExpectedEvidence(
                "Evidence of leadership approval",
                (TYPE_RECORD, TYPE_ATTESTATION),
            ),
            ExpectedEvidence(
                "Evidence it was communicated to staff",
                (TYPE_RECORD,),
            ),
        ),
        checklist=(
            "Draft the AI policy",
            "Review it with legal and engineering",
            "Obtain leadership approval",
            "Communicate it to staff",
            "Upload the approved policy",
        ),
        due_in_days=30,
    ),
}


# Gap kind decides how the work is framed when there is no playbook.
_KIND_FRAMING: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "no_control": (
        "No control is mapped to this requirement, so there is nothing recorded that could "
        "demonstrate it.",
        "Define a control describing how the organization meets this requirement, map it, "
        "and attach the evidence.",
        (
            "Decide what the organization actually does to meet this requirement",
            "Create a control describing it",
            "Map the control to this requirement",
            "Upload the document that demonstrates it",
        ),
    ),
    "evidence_missing": (
        "A control is mapped to this requirement but nothing on file demonstrates it.",
        "Produce or locate the document that demonstrates this control and upload it.",
        (
            "Identify the document that demonstrates this control",
            "Produce it if it does not exist yet",
            "Have it approved by whoever owns it",
            "Upload it — Veyntra will map it automatically",
        ),
    ),
    # No "work out which part is uncovered" here. Where this framing is
    # used at all the coverage analysis has already named the unmet
    # conditions, and build_plan writes them into the problem and the
    # checklist — see `missing_conditions`. This is only the shape the
    # sentence takes before they are substituted in.
    "evidence_partial": (
        "Evidence is on file for this requirement, but it does not include everything a "
        "complete answer needs.",
        "Supply the specific evidence named below and upload it.",
        (
            "Produce the evidence named above",
            "Have it approved by whoever owns it",
            "Upload it — Veyntra will map it automatically",
        ),
    ),
    "assessment_failed": (
        "The most recent assessment of the mapped control concluded that it failed.",
        "Address the finding recorded on that assessment, then supply corrected evidence.",
        (
            "Read the failing assessment and its notes",
            "Fix the underlying issue",
            "Produce evidence of the fix",
            "Upload it and reassess",
        ),
    ),
}

# Severity maps to a suggested priority. Kept explicit rather than reusing
# the severity string directly: they are different vocabularies and a task
# board reads "high priority", not "high severity".
_PRIORITY_BY_SEVERITY = {"high": "high", "medium": "normal", "low": "low"}


def _mid_sentence(item: str) -> str:
    """Lowercase a leading word, unless it is an acronym.

    "AI literacy training policy" appearing mid-sentence as "aI literacy"
    is the kind of detail that makes generated prose read as generated.
    A second capital in the first word means it is an acronym, not a
    sentence opening.
    """
    if not item:
        return item
    first = item.split(" ", 1)[0]
    if len(first) > 1 and first[1:].lower() != first[1:]:
        return item
    return item[0].lower() + item[1:]


def sentence_list(items: list[str], conjunction: str = "and") -> str:
    """Join for prose, not for a log line.

    These strings are read mid-sentence by someone who does not work in
    compliance daily, so a comma-joined list with a trailing comma reads
    as truncated output rather than as English.
    """
    lowered = [_mid_sentence(item) for item in items]
    if not lowered:
        return ""
    if len(lowered) == 1:
        return lowered[0]
    return ", ".join(lowered[:-1]) + f" {conjunction} {lowered[-1]}"


def build_plan(
    *,
    framework_key: str,
    framework_name: str,
    requirement_code: str,
    requirement_title: str,
    requirement_description: str | None,
    gap_kind: str,
    severity: str,
    control_title: str | None,
    evidence_reviewed: list[str],
    affected_ai_systems: list[str],
    missing_conditions: list[str] | None = None,
) -> RemediationPlan:
    """Assemble the plan for one gap.

    Prefers a playbook written against the specific requirement; falls
    back to framing derived from the gap kind. The fallback is
    deliberately modest — where there is no playbook it says what it can
    from the requirement and asks for the evidence, rather than inventing
    steps nobody can stand behind.
    """
    playbook = PLAYBOOKS.get((framework_key, requirement_code))
    default_problem, default_action, default_checklist = _KIND_FRAMING.get(
        gap_kind, _KIND_FRAMING["evidence_missing"]
    )

    unmet = list(missing_conditions or [])

    if playbook is not None:
        problem = playbook.problem
        action = playbook.action
        owner = playbook.owner
        required_evidence = [item.description for item in playbook.required_evidence]
        checklist = list(playbook.checklist)
        due_in_days = playbook.due_in_days
    else:
        problem = default_problem
        action = default_action
        owner = OWNER_COMPLIANCE
        required_evidence = [
            f"A document demonstrating {requirement_code} — {requirement_title}"
        ]
        checklist = list(default_checklist)
        due_in_days = 30

    # The whole point of the coverage analysis: when it can name what is
    # unmet, the finding says so. A gap that reports "some evidence does
    # not cover the whole requirement" has told the reader nothing they
    # could not see, and hands them the analysis we were meant to do.
    if unmet:
        held = [item for item in required_evidence if item not in unmet]
        problem = (
            (
                f"The evidence on file covers {sentence_list(held)}, but "
                if held
                else "The evidence on file does not yet demonstrate this requirement: "
            )
            + f"nothing on file provides {sentence_list(unmet, 'or')}."
        )
        action = f"Supply {sentence_list(unmet)}, and upload it as evidence."
        # The playbook's own steps are real-world work — "run a
        # restoration test and record the result", "deliver the
        # training", "test the override path works". Replacing them with
        # "Produce <the missing document>" turned a compliance programme
        # into a filing exercise, which is exactly the failure mode this
        # module was written to avoid. Where a playbook exists its steps
        # stand; only the generic fallback has to build a list.
        if playbook is None:
            checklist = [
                *(f"Produce {item}" for item in unmet),
                "Have it approved by whoever owns it",
                "Upload it — Veyntra will map it automatically",
            ]

    why = (
        f"{framework_name} {requirement_code} requires {requirement_title.lower()}. "
        + (
            f"The control '{control_title}' is mapped to it, but "
            if control_title
            else "No control is mapped to it, so "
        )
        + (
            f"the {len(evidence_reviewed)} document(s) on file do not demonstrate it in full."
            if evidence_reviewed
            else "nothing on file demonstrates it."
        )
    )

    missing = (
        "Evidence that would close this: "
        + "; ".join(unmet if unmet else required_evidence)
        + "."
    )

    # Every plan ends by getting the evidence back into the system, because
    # that is what actually closes the gap — the work being done elsewhere
    # and never uploaded leaves the position unchanged.
    if not checklist or "upload" not in checklist[-1].lower():
        checklist = [*checklist, "Upload the evidence so the control is reassessed"]

    return RemediationPlan(
        problem=problem,
        why=why,
        action=action,
        owner=owner,
        priority=_PRIORITY_BY_SEVERITY.get(severity, "normal"),
        due_in_days=due_in_days,
        required_evidence=required_evidence,
        checklist=checklist,
        evidence_reviewed=evidence_reviewed,
        missing_conditions=unmet,
        missing_evidence=missing,
        requirement_code=requirement_code,
        requirement_title=requirement_title,
        framework_name=framework_name,
        control_title=control_title,
        affected_ai_systems=affected_ai_systems,
    )


def expectations_for(
    framework_key: str, reference_code: str
) -> tuple[ExpectedEvidence, ...]:
    """What a complete answer to this requirement contains.

    Empty where no playbook has been written. Callers must treat that as
    "we cannot say what is missing" rather than "nothing is missing" —
    the two conclusions are opposite and only one of them is honest.
    """
    playbook = PLAYBOOKS.get((framework_key, reference_code))
    return playbook.required_evidence if playbook else ()


def render_description(plan: RemediationPlan) -> str:
    """The task description, as a person reads it on a task board."""
    lines = [
        "PROBLEM",
        plan.problem,
        "",
        "WHY THIS MATTERS",
        plan.why,
        "",
        "WHAT TO DO",
        plan.action,
        "",
        "EVIDENCE THAT WOULD CLOSE THIS",
    ]
    lines += [
        f"  - {item}"
        for item in (plan.missing_conditions or plan.required_evidence)
    ]
    if plan.evidence_reviewed:
        lines += ["", "ALREADY REVIEWED"]
        lines += [f"  - {item}" for item in plan.evidence_reviewed]
    if plan.affected_ai_systems:
        lines += ["", "AFFECTED AI SYSTEMS"]
        lines += [f"  - {item}" for item in plan.affected_ai_systems]
    lines += ["", f"Suggested owner: {plan.owner}"]
    return "\n".join(lines)


__all__ = [
    "PLAYBOOKS",
    "ExpectedEvidence",
    "Playbook",
    "expectations_for",
    "sentence_list",
    "RemediationPlan",
    "build_plan",
    "render_description",
]
