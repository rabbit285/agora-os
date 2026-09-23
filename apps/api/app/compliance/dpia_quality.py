"""What separates a completed assessment from a formal-looking one.

The lifecycle was right and the content was not. Veyntra drafted
*instructions* — "State why this processing is necessary", "Assess
whether the data collected is limited" — a reviewer pressed Approve, and
the DPIA completed carrying guidance where its argument should be. A
risk conclusion passed on the rationale "ok". A medical-leave assessment
completed while reporting "no personal-data categories are recorded".

Every check here exists to stop the same shape of failure: **absent
information turning into a positive conclusion.** No categories recorded
does not mean no sensitive data. No risks entered does not mean no
material risk. An unedited prompt does not mean somebody assessed
anything.

Three rules run through the file.

**Guidance is not an answer.** Text that tells the reader what to write
is detected structurally — imperative openers, second-person address,
Veyntra's own draft scaffolding — not by length, which a paragraph of
padding would pass.

**Substance is not word count.** A rationale is rejected for saying
nothing ("ok", "n/a", "fine"), for restating the conclusion it is meant
to justify, and for failing to engage any of the factors that make a
privacy conclusion defensible. Length alone is never the test.

**Veyntra detects; a person decides.** Health signals in a processing
name raise a question for a human to answer. This module never records
an Article 9 conclusion, never decides that special-category data is
absent, and never resolves a gap by assuming the benign reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- guidance, as opposed to an assessment ------------------------------

# Openers that address the reader rather than describe the processing.
# An assessment says what is true; guidance says what somebody should do
# about it, and only the first can be approved as a finding.
_IMPERATIVE_OPENERS = (
    "state ",
    "assess ",
    "describe ",
    "explain ",
    "record ",
    "confirm ",
    "consider ",
    "review ",
    "identify ",
    "document ",
    "specify ",
    "provide ",
    "outline ",
    "complete ",
    "fill in",
    "add ",
    "enter ",
    "list ",
    "set out",
    "justify ",
    "needs human input",
    "to be completed",
    "tbd",
    "todo",
)

# Phrases that mean the text is still Veyntra's scaffolding, wherever
# they appear. These are the sentences the old drafts ended on.
_GUIDANCE_PHRASES = (
    "veyntra cannot make this argument",
    "it is the controller's",
    "needs human input",
    "veyntra has no record of either",
    "there is nothing to assess",
    "nothing is recorded about this processing yet",
    "to be completed",
    "lorem ipsum",
)

# Second-person address. An assessment is written about the processing,
# not to the person filling it in.
_SECOND_PERSON = re.compile(r"\b(you|your|yours)\b", re.IGNORECASE)

DRAFT_MARKER_PATTERN = re.compile(r"^\[Veyntra draft[^\]]*\]\s*", re.IGNORECASE)


def strip_marker(text: str) -> str:
    return DRAFT_MARKER_PATTERN.sub("", text or "").strip()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def is_instructional(text: str) -> bool:
    """True when the text tells somebody what to write rather than saying it.

    Structural rather than statistical: a long paragraph of instructions
    is still instructions, and a short factual finding is still a
    finding.
    """
    body = strip_marker(text).lower()
    if not body:
        return False
    if any(phrase in body for phrase in _GUIDANCE_PHRASES):
        return True
    # Any sentence that opens in the imperative is an instruction, even
    # where the rest of the paragraph is factual — the old drafts put
    # exactly one such sentence at the end.
    return any(
        sentence.lower().startswith(_IMPERATIVE_OPENERS)
        for sentence in _sentences(strip_marker(text))
    )


# --- non-substantive text -----------------------------------------------

# Answers that occupy the field without saying anything. Matched as the
# whole content, so a rationale that *contains* "n/a" while explaining
# something is unaffected.
_EMPTY_ANSWERS = {
    "ok",
    "okay",
    "none",
    "no",
    "yes",
    "n/a",
    "na",
    "nil",
    "null",
    "nothing",
    "test",
    "testing",
    "done",
    "fine",
    "good",
    "asdf",
    "x",
    "-",
    ".",
    "tbd",
    "todo",
    "n/a.",
    "no risk",
    "no risks",
    "low risk",
    "not applicable",
    "no comment",
    "as above",
    "see above",
}


def is_empty_answer(text: str) -> bool:
    """True for content that fills the field and answers nothing."""
    body = re.sub(r"[^a-z0-9/ ]", "", strip_marker(text).lower()).strip()
    if not body:
        return True
    if body in {answer.replace(".", "") for answer in _EMPTY_ANSWERS}:
        return True
    # A handful of words with no verb is a label, not an assessment.
    words = body.split()
    return len(words) <= 3 and body in _EMPTY_ANSWERS


# --- Article 35(7) sections ---------------------------------------------

SECTION_LABELS = {
    "processing_description": "the description of the processing",
    "necessity_assessment": "the necessity assessment",
    "proportionality_assessment": "the proportionality assessment",
    "consultation_notes": "the consultation record",
}

# What each section has to actually engage with. Used to explain a
# refusal, and rendered as the guidance a reviewer works against — kept
# apart from the answer so it can never be approved as one.
SECTION_GUIDANCE = {
    "processing_description": (
        "The nature, scope, context and purposes of the processing: what "
        "data, about whom, through which systems and processors, and for "
        "how long."
    ),
    "necessity_assessment": (
        "Why the processing is necessary for the stated purpose, and why "
        "a less intrusive alternative would not achieve it."
    ),
    "proportionality_assessment": (
        "Whether the data collected is limited to what the purpose "
        "requires, whether the retention period is the shortest that "
        "serves it, and what safeguards apply."
    ),
    "consultation_notes": (
        "DPO advice, and where relevant the views of data subjects or "
        "their representatives."
    ),
}


def section_problem(section: str, text: str | None) -> str | None:
    """Why this section cannot be approved as an assessment, or None.

    Guidance is refused before length is considered: the failure being
    prevented is a reviewer approving Veyntra's prompt, which is a long
    piece of text and would pass any word count.
    """
    label = SECTION_LABELS.get(section, "this section")
    body = strip_marker(text or "")
    if not body:
        return f"Nothing is recorded for {label}."
    if is_instructional(body):
        return (
            f"This is guidance, not a completed assessment. {label.capitalize()} "
            "still contains instructions about what to write rather than the "
            "assessment itself."
        )
    if is_empty_answer(body):
        return (
            f"{label.capitalize()} does not contain a substantive assessment."
        )
    if len(body.split()) < 12:
        # A floor, not the test. Everything above has already rejected
        # the failures that length cannot catch.
        return (
            f"{label.capitalize()} is too brief to be an assessment somebody "
            "could rely on later."
        )
    if _SECOND_PERSON.search(body) and len(_sentences(body)) <= 2:
        return (
            f"{label.capitalize()} reads as an instruction to the reader "
            "rather than a finding about the processing."
        )
    return None


# --- the "no material risks" rationale ----------------------------------

# Factors a defensible "nothing material here" argument engages with.
# Not a checklist to satisfy mechanically — the test is that the
# rationale addresses *something* concrete about why this processing is
# low risk, rather than asserting the conclusion again.
_RATIONALE_FACTORS = (
    ("purpose", ("purpose", "limited to", "only used", "solely for", "confined")),
    ("data", ("data", "information", "categor", "field", "record", "personal")),
    ("sensitivity", ("sensitive", "special categor", "health", "medical", "minim")),
    ("access", ("access", "restricted", "permission", "role", "authoris", "authoriz")),
    ("retention", ("retention", "retained", "deleted", "erasure", "kept for")),
    ("safeguards", ("safeguard", "control", "encrypt", "pseudonym", "protect", "secur")),
    ("automation", ("automated", "profiling", "decision", "algorithm")),
    ("scope", ("volume", "scale", "number of", "small", "few", "scope")),
    ("exposure", ("vendor", "processor", "transfer", "third part", "shared")),
)


def rationale_problem(text: str | None) -> str | None:
    """Why this rationale is not one an auditor could rely on, or None.

    "ok" is the case that prompted this, but a character count would
    also pass "no material risks were identified" — a restatement of the
    conclusion rather than a reason for it. So the test is whether the
    text engages with anything concrete about the processing.
    """
    body = strip_marker(text or "")
    if not body:
        return "A rationale is required."
    if is_empty_answer(body):
        return (
            "That is not a rationale somebody could rely on later. Explain "
            "why this processing does not present material privacy risks — "
            "what it is limited to, who can reach the data, how long it is "
            "kept, and what reduces the impact on the people involved."
        )
    if is_instructional(body):
        return (
            "This is guidance rather than a rationale. Record the reasoning "
            "itself."
        )

    words = body.split()
    if len(words) < 15:
        return (
            "The rationale is too brief to explain a conclusion that no "
            "material risk exists. Address what the processing is limited "
            "to, who can access the data, how long it is kept, and what "
            "safeguards apply."
        )

    lowered = body.lower()
    matched = [
        name
        for name, needles in _RATIONALE_FACTORS
        if any(needle in lowered for needle in needles)
    ]
    if len(matched) < 2:
        return (
            "The rationale restates the conclusion without supporting it. A "
            "defensible one addresses the specifics — the nature and scope "
            "of the processing, the sensitivity of the data, access "
            "controls, retention, automated decision-making, vendor or "
            "transfer exposure, and the remaining impact on individuals."
        )
    return None


# --- processing facts an assessment cannot be written without -----------


@dataclass
class MissingFact:
    """One piece of context the assessment needs and does not have."""

    code: str
    message: str
    # Where to go and fix it.
    href: str


def missing_facts(context, *, activity_id: str | None = None) -> list[MissingFact]:
    """Core facts absent from the processing record.

    Missing context is not a benign finding. A DPIA written against a
    record with no data categories cannot say what was assessed, and
    completing it would produce a document that answers none of the
    questions an auditor asks of it.
    """
    where = (
        f"/compliance/privacy/processing-activities?activity={activity_id}"
        if activity_id
        else "/compliance/privacy/processing-activities"
    )
    gaps: list[MissingFact] = []
    if not (context.purpose or "").strip():
        gaps.append(
            MissingFact(
                "missing_purpose",
                "No purpose is recorded for this processing.",
                where,
            )
        )
    if not (context.data_subjects or "").strip():
        gaps.append(
            MissingFact(
                "missing_data_subjects",
                "The people this processing concerns have not been recorded.",
                where,
            )
        )
    if not context.data_categories:
        gaps.append(
            MissingFact(
                "missing_data_categories",
                "Personal-data categories have not been recorded, so the "
                "assessment cannot say what data was assessed.",
                where,
            )
        )
    if not (context.retention or "").strip():
        gaps.append(
            MissingFact(
                "missing_retention",
                "No retention period is recorded, so proportionality cannot "
                "be assessed against how long the data is kept.",
                where,
            )
        )
    return gaps


# --- special-category signals -------------------------------------------

# Words in a processing record that suggest Article 9 data may be in
# scope. Detection only: whether Article 9 applies, and on what
# condition, is a legal conclusion this module never reaches.
_SPECIAL_SIGNALS: dict[str, tuple[str, ...]] = {
    "health or medical information": (
        "medical",
        "health",
        "sick",
        "sickness",
        "illness",
        "injury",
        "disability",
        "occupational health",
        "fit note",
        "doctor",
        "clinical",
        "diagnos",
        "treatment",
        "patient",
        "mental health",
        "wellbeing",
    ),
    "trade-union membership": ("trade union", "union membership"),
    "racial or ethnic origin": ("ethnic", "race ", "racial", "nationality"),
    "religious or philosophical beliefs": ("religio", "belief", "faith"),
    "sex life or sexual orientation": ("sexual", "sex life", "orientation"),
    "biometric or genetic data": ("biometric", "genetic", "fingerprint", "facial recognition"),
    "criminal convictions or offences": ("criminal", "conviction", "offence", "offense"),
    "political opinions": ("political", "party membership"),
}

# "Leave" alone is ordinary HR; paired with these it is not.
_LEAVE_CONTEXT = ("medical leave", "sick leave", "sickness absence", "occupational")


@dataclass
class SpecialCategorySignal:
    """A hint that Article 9 data may be involved, and where it came from."""

    kind: str
    # The recorded text the hint was read out of, so a reviewer can
    # check the detection rather than take it on trust.
    evidence: str


def special_category_signals(context) -> list[SpecialCategorySignal]:
    """Article 9 hints in the recorded processing.

    Detection, never a determination. A name like "Employee medical-leave
    administration" strongly suggests health data, and the failure this
    prevents is the product reading "no categories recorded" and
    concluding there is nothing sensitive here.
    """
    haystacks = [
        ("the activity name", context.title or ""),
        ("the recorded purpose", context.purpose or ""),
        ("the data subjects", context.data_subjects or ""),
    ]
    haystacks.extend(
        ("a recorded data category", category) for category in context.data_categories
    )
    haystacks.extend(("a linked AI system", name) for name in context.ai_systems)

    found: dict[str, SpecialCategorySignal] = {}
    for where, text in haystacks:
        lowered = (text or "").lower()
        if not lowered:
            continue
        for kind, needles in _SPECIAL_SIGNALS.items():
            if kind in found:
                continue
            hit = next((needle for needle in needles if needle in lowered), None)
            if hit is None and kind == "health or medical information":
                hit = next((phrase for phrase in _LEAVE_CONTEXT if phrase in lowered), None)
            if hit is not None:
                found[kind] = SpecialCategorySignal(
                    kind=kind, evidence=f"{where}: “{text.strip()}”"
                )
    return list(found.values())


__all__ = [
    "SECTION_GUIDANCE",
    "SECTION_LABELS",
    "MissingFact",
    "SpecialCategorySignal",
    "is_empty_answer",
    "is_instructional",
    "missing_facts",
    "rationale_problem",
    "section_problem",
    "special_category_signals",
    "strip_marker",
]
