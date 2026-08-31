"""What an audit against each framework actually covers.

A suggestion, for the box somebody would otherwise leave empty or fill
with the wrong standard's vocabulary — an audit scoped as "AI governance,
human oversight, monitoring" is not a GDPR audit however clearly it is
labelled one, and a reader of the report later has no way to tell the
mislabelling from a deliberate choice.

These are descriptions of subject matter, not claims. Each names the
domains the framework's own requirements fall into, so the sentence
matches the requirements the audit will actually scope.

Never applied over something a person wrote. A scope statement is the
auditor's description of their own engagement, and replacing it because
they changed a dropdown would overwrite the one field in the form that
only they can fill in.
"""

from __future__ import annotations

SUGGESTED_SCOPE = {
    "gdpr": (
        "Privacy governance, lawful basis for processing, data subject "
        "rights, processor management, security of processing, personal "
        "data breach response, data protection impact assessments, "
        "retention, and international transfers."
    ),
    "eu_ai_act": (
        "AI system classification, prohibited practices, high-risk system "
        "obligations, risk management, data governance, technical "
        "documentation, human oversight, transparency, and post-market "
        "monitoring."
    ),
    "iso42001": (
        "AI governance, risk management, roles and responsibilities, AI "
        "system lifecycle controls, impact assessment, monitoring and "
        "measurement, and continual improvement."
    ),
    "iso27001": (
        "Information security management system governance, risk "
        "assessment and treatment, Annex A control implementation, "
        "access control, operations security, supplier relationships, "
        "incident management, and continuity."
    ),
    "soc2": (
        "Trust services criteria for security, availability, processing "
        "integrity, confidentiality and privacy, including the control "
        "environment, risk assessment, monitoring, and logical and "
        "physical access controls."
    ),
    "nis2": (
        "Cybersecurity risk management measures, governance and "
        "accountability, incident handling and reporting, business "
        "continuity, supply chain security, and vulnerability handling."
    ),
    "dora": (
        "ICT risk management, ICT-related incident management and "
        "reporting, digital operational resilience testing, third-party "
        "ICT risk, and information sharing arrangements."
    ),
}

# What a custom audit's scope box says before anybody fills it in. No
# suggestion, because the whole point of a custom audit is that only the
# person running it knows what it covers.
CUSTOM_PLACEHOLDER = "What this audit covers"


def suggested_scope(framework_key: str | None) -> str | None:
    """The scope wording for this framework, if we have one.

    None for anything unrecognised, including an organization's own
    custom framework — writing a plausible-sounding scope for a standard
    this code has never seen would be inventing the subject matter of
    somebody's audit.
    """
    if not framework_key:
        return None
    return SUGGESTED_SCOPE.get(framework_key.strip().lower())


__all__ = ["CUSTOM_PLACEHOLDER", "SUGGESTED_SCOPE", "suggested_scope"]
