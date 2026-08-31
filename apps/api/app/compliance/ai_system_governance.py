"""Per-system AI governance: what is documented, what is missing, what to do.

An AI inventory that lists names and vendors is an asset register. The
question a customer is actually asked by an enterprise buyer — "which AI
systems process our information, and how are they governed" — needs a
per-system answer: what we know about it, what we do not, and what is
outstanding.

**Deterministic, not generated.** Completeness is a count of declared
facts. Required actions are rules over those facts and over what is
already linked to the system. A model is not consulted here, because the
output is a checklist the customer will be held to, and it has to be the
same checklist every time they look.

**Missing documentation is reported as missing, never as a violation.**
An undocumented oversight arrangement means we cannot show one, which is
not the same as there being none. The wording throughout says what is
absent from the record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import AIAssessment, AIIncident, AISystem, Risk

# Facts an inventory entry needs before anyone can reason about the
# system. Ordered as they are asked in the UI so a customer filling them
# in works top to bottom. `label` is what appears in "still missing".
DOCUMENTATION_FIELDS: tuple[tuple[str, str], ...] = (
    ("purpose", "What the system is for"),
    ("description", "A description of how it works"),
    ("model_name", "The model behind it"),
    ("vendor", "The provider"),
    ("geography", "Where it operates"),
    ("human_oversight", "How a person oversees it"),
    ("business_owner_id", "A business owner"),
    ("technical_owner_id", "A technical owner"),
    ("affected_users", "Who is affected by it"),
    ("processed_data", "What data it processes"),
)

# Deployment states where an ungoverned system is actually reaching
# people. A gap on a system still in development is a planning item; the
# same gap in production is live exposure, and the two should not be
# reported with equal weight.
LIVE_DEPLOYMENT_STATES = frozenset({"pilot", "production"})


@dataclass
class RequiredAction:
    title: str
    detail: str
    # high | medium | low
    priority: str
    # Which obligation drives this, in the customer's terms. Every action
    # names one — an action nobody can trace to a requirement is busywork.
    basis: str


@dataclass
class AISystemGovernance:
    ai_system_id: uuid.UUID
    name: str
    risk_classification: str
    deployment_status: str
    vendor: str | None
    model_name: str | None

    documentation_completeness: int
    missing_documentation: list[str] = field(default_factory=list)
    applicable_regulations: list[str] = field(default_factory=list)
    open_risk_count: int = 0
    open_incident_count: int = 0
    has_current_screening: bool = False
    required_actions: list[RequiredAction] = field(default_factory=list)
    # A readiness figure per system, computed the same way for every
    # system so two are comparable. Never a model's opinion.
    readiness_percent: float = 0.0
    explanation: str = ""


def _declared(system: AISystem, attribute: str) -> bool:
    value = getattr(system, attribute, None)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True


def documentation_state(system: AISystem) -> tuple[int, list[str]]:
    """How much of the inventory entry is filled in, and what is not.

    Returns a percentage and the human-readable labels of what is still
    missing, so the UI never has to show a bare score with nothing to act
    on.
    """
    missing = [label for attribute, label in DOCUMENTATION_FIELDS if not _declared(system, attribute)]
    filled = len(DOCUMENTATION_FIELDS) - len(missing)
    percent = round(100 * filled / len(DOCUMENTATION_FIELDS))
    return percent, missing


def applicable_regulations(system: AISystem) -> list[str]:
    """Which regulations reach this specific system, from its own facts.

    Deliberately narrow. A system that touches no personal data and makes
    no decisions about people does not get GDPR listed against it just
    because the organization is subject to GDPR overall — that would make
    the field meaningless on every card.
    """
    regulations: list[str] = ["EU AI Act"]
    if system.personal_data_processed or system.automated_decision_making:
        regulations.append("GDPR")
    return regulations


def required_actions(
    system: AISystem,
    *,
    missing_documentation: list[str],
    has_current_screening: bool,
    open_incident_count: int,
) -> list[RequiredAction]:
    """What is outstanding for this system, strongest first.

    Rules over declared facts. Each action names the obligation behind it
    so the customer can see why it is being asked of them, and none of
    them assert that the organization is in breach of anything.
    """
    actions: list[RequiredAction] = []
    live = system.deployment_status in LIVE_DEPLOYMENT_STATES

    if not has_current_screening:
        actions.append(
            RequiredAction(
                title="Screen this system under the EU AI Act",
                detail=(
                    "No screening is on record, so its risk classification has not been "
                    "established from its actual purpose and use."
                ),
                priority="high" if live else "medium",
                basis="EU AI Act Art. 6",
            )
        )

    if system.risk_classification in ("high", "unacceptable") and not _declared(
        system, "human_oversight"
    ):
        actions.append(
            RequiredAction(
                title="Document how a person oversees this system",
                detail=(
                    "This system is classified high risk and the record does not describe "
                    "how someone can interpret its output, intervene, or interrupt it."
                ),
                priority="high",
                basis="EU AI Act Art. 14",
            )
        )

    if system.automated_decision_making and system.personal_data_processed:
        actions.append(
            RequiredAction(
                title="Confirm the safeguards for automated decisions",
                detail=(
                    "This system makes automated decisions about people. Record the lawful "
                    "condition, and how someone can obtain human intervention and contest a "
                    "decision."
                ),
                priority="high",
                basis="GDPR Art. 22",
            )
        )

    if system.sensitive_data_processed:
        actions.append(
            RequiredAction(
                title="Record the condition for processing sensitive data",
                detail=(
                    "This system processes special category data, which needs an Article "
                    "9(2) condition recorded alongside its lawful basis."
                ),
                priority="high",
                basis="GDPR Art. 9",
            )
        )

    if system.is_external and not _declared(system, "human_oversight"):
        actions.append(
            RequiredAction(
                title="Describe oversight for a customer-facing system",
                detail=(
                    "People outside the organization interact with this system, and the "
                    "record does not say who supervises it."
                ),
                priority="medium",
                basis="EU AI Act Art. 14",
            )
        )

    if open_incident_count:
        actions.append(
            RequiredAction(
                title=f"Resolve {open_incident_count} open incident"
                f"{'s' if open_incident_count != 1 else ''}",
                detail="Incidents logged against this system have not been closed out.",
                priority="high",
                basis="EU AI Act Art. 73",
            )
        )

    if missing_documentation:
        actions.append(
            RequiredAction(
                title="Complete the inventory entry",
                detail="Still missing: " + ", ".join(missing_documentation[:4]).lower() + ".",
                priority="medium" if live else "low",
                basis="EU AI Act Art. 11",
            )
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(actions, key=lambda a: priority_order.get(a.priority, 3))


def _readiness(
    *,
    documentation_completeness: int,
    has_current_screening: bool,
    open_actions: int,
    open_incident_count: int,
) -> tuple[float, str]:
    """A per-system readiness figure that shows its own arithmetic.

    Weighted toward the two things that actually establish governance —
    a screening on record and a complete entry — with outstanding actions
    and open incidents taking it back down. Conservative by construction:
    a system with nothing recorded cannot score above the documentation
    it lacks.
    """
    documentation_share = documentation_completeness * 0.6
    screening_share = 40.0 if has_current_screening else 0.0
    raw = documentation_share + screening_share

    penalty = min(open_actions * 5.0, 25.0) + min(open_incident_count * 10.0, 20.0)
    percent = max(0.0, round(raw - penalty, 1))

    parts = [f"{documentation_completeness}% of its inventory entry is filled in"]
    parts.append(
        "a screening is on record" if has_current_screening else "no screening is on record"
    )
    if open_actions:
        parts.append(f"{open_actions} action{'s' if open_actions != 1 else ''} outstanding")
    if open_incident_count:
        parts.append(
            f"{open_incident_count} open incident{'s' if open_incident_count != 1 else ''}"
        )

    detail = ", ".join(parts[:-1]) + f" and {parts[-1]}" if len(parts) > 1 else parts[0]
    explanation = (
        f"{percent}% because {detail}. This measures what is documented and assessed in "
        "Veyntra, not a conclusion about whether the system is lawful."
    )
    return percent, explanation


async def assess_ai_system(db: AsyncSession, *, system: AISystem) -> AISystemGovernance:
    """Everything the AI Systems screen needs about one system."""
    completeness, missing = documentation_state(system)

    open_risks = int(
        await db.scalar(
            select(func.count(Risk.id)).where(
                Risk.ai_system_id == system.id, Risk.status == "open"
            )
        )
        or 0
    )
    open_incidents = int(
        await db.scalar(
            select(func.count(AIIncident.id)).where(
                AIIncident.ai_system_id == system.id, AIIncident.status != "closed"
            )
        )
        or 0
    )
    screening = await db.scalar(
        select(func.count(AIAssessment.id)).where(
            AIAssessment.ai_system_id == system.id,
            AIAssessment.assessment_type == "eu_ai_act_screening",
        )
    )
    has_screening = bool(screening)

    actions = required_actions(
        system,
        missing_documentation=missing,
        has_current_screening=has_screening,
        open_incident_count=open_incidents,
    )
    percent, explanation = _readiness(
        documentation_completeness=completeness,
        has_current_screening=has_screening,
        open_actions=len(actions),
        open_incident_count=open_incidents,
    )

    return AISystemGovernance(
        ai_system_id=system.id,
        name=system.name,
        risk_classification=system.risk_classification,
        deployment_status=system.deployment_status,
        vendor=system.vendor,
        model_name=system.model_name,
        documentation_completeness=completeness,
        missing_documentation=missing,
        applicable_regulations=applicable_regulations(system),
        open_risk_count=open_risks,
        open_incident_count=open_incidents,
        has_current_screening=has_screening,
        required_actions=actions,
        readiness_percent=percent,
        explanation=explanation,
    )


__all__ = [
    "DOCUMENTATION_FIELDS",
    "LIVE_DEPLOYMENT_STATES",
    "AISystemGovernance",
    "RequiredAction",
    "applicable_regulations",
    "assess_ai_system",
    "documentation_state",
    "required_actions",
]
