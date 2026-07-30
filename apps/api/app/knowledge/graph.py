"""Organization Knowledge Graph (spec §10): "Relationships must be
queryable" over the entities every other module already links together via
real foreign keys (the same cross-module hooks spec §80/§69 wire up:
Account -> Contact -> Opportunity -> Customer -> Ticket -> SecurityReview,
Vendor -> Risk, AI System -> DPIA -> AI Incident, etc.).

This is deliberately a *read-only traversal view* over the existing
relational data, not a second, duplicated graph store — a parallel graph
database that has to be kept in sync with 20 tables' worth of foreign keys
would be a second source of truth, which is a worse design than querying
the first one directly. "Gives AI richer context" (spec §10) is served by
callers (e.g. a future Copilot tool) fetching a node's neighborhood
through `get_entity_graph` rather than the graph needing to exist as its
own storage.

Entity/relationship *extraction from document text* (spec §11's ingestion
pipeline step) is a separate, narrower concern from this cross-module
structural graph, which only concerns records that already exist as rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    DPIA,
    AIIncident,
    AISystem,
    Audit,
    AuditFinding,
    Control,
    DataTransfer,
    Evidence,
    Questionnaire,
    Risk,
    SecurityReview,
    Vendor,
    VendorAssessment,
)
from app.sales.models import Account, Contact, Lead, Opportunity
from app.secops.models import SecurityAlert, SecurityAsset, SecurityFinding, SecurityIncident
from app.support.models import Customer, Ticket


@dataclass
class GraphNode:
    entity_type: str
    id: str
    label: str


@dataclass
class GraphEdge:
    relation: str
    node: GraphNode


@dataclass
class GraphResult:
    node: GraphNode
    edges: list[GraphEdge] = field(default_factory=list)


class UnknownEntityTypeError(Exception):
    pass


async def _get(
    db: AsyncSession, model: type[Any], entity_id: uuid.UUID, organization_id: uuid.UUID
) -> Any | None:
    obj = await db.get(model, entity_id)
    if obj is None or obj.organization_id != organization_id:
        return None
    return obj


async def _many(db: AsyncSession, model: type[Any], **equals: Any) -> list[Any]:
    stmt = select(model)
    for key, value in equals.items():
        stmt = stmt.where(getattr(model, key) == value)
    return list((await db.execute(stmt)).scalars().all())


def _node(entity_type: str, obj: Any, label_attr: str = "title") -> GraphNode:
    label = getattr(obj, label_attr, None) or getattr(obj, "name", None) or str(obj.id)
    return GraphNode(entity_type=entity_type, id=str(obj.id), label=str(label))


async def _edge_if_exists(
    db: AsyncSession,
    *,
    relation: str,
    model: type[Any],
    entity_type: str,
    entity_id: uuid.UUID | None,
    organization_id: uuid.UUID,
) -> GraphEdge | None:
    if entity_id is None:
        return None
    obj = await _get(db, model, entity_id, organization_id)
    if obj is None:
        return None
    return GraphEdge(relation=relation, node=_node(entity_type, obj))


GraphLoader = Callable[[AsyncSession, uuid.UUID, uuid.UUID], Awaitable["GraphResult | None"]]


async def get_entity_graph(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> GraphResult | None:
    """Returns the given entity plus its one-hop neighbors, or None if the
    entity doesn't exist (or belongs to a different organization — this
    function is tenant-scoped exactly like every other query in the app)."""
    loader = _LOADERS.get(entity_type)
    if loader is None:
        raise UnknownEntityTypeError(entity_type)
    return await loader(db, organization_id, entity_id)


async def _load_sales_account(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    account = await _get(db, Account, entity_id, organization_id)
    if account is None:
        return None
    edges = [
        GraphEdge(relation="contact", node=_node("sales_contact", c, "full_name"))
        for c in await _many(db, Contact, account_id=account.id, organization_id=organization_id)
    ]
    edges += [
        GraphEdge(relation="opportunity", node=_node("sales_opportunity", o, "title"))
        for o in await _many(
            db, Opportunity, account_id=account.id, organization_id=organization_id
        )
    ]
    customers = await _many(
        db, Customer, sales_account_id=account.id, organization_id=organization_id
    )
    edges += [
        GraphEdge(relation="support_customer", node=_node("support_customer", c)) for c in customers
    ]
    return GraphResult(node=_node("sales_account", account), edges=edges)


async def _load_sales_contact(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    contact = await _get(db, Contact, entity_id, organization_id)
    if contact is None:
        return None
    edges = []
    account_edge = await _edge_if_exists(
        db,
        relation="account",
        model=Account,
        entity_type="sales_account",
        entity_id=contact.account_id,
        organization_id=organization_id,
    )
    if account_edge:
        edges.append(account_edge)
    return GraphResult(node=_node("sales_contact", contact, "full_name"), edges=edges)


async def _load_sales_lead(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    lead = await _get(db, Lead, entity_id, organization_id)
    if lead is None:
        return None
    edges = []
    for model, entity_type, fk in (
        (Account, "sales_account", lead.account_id),
        (Contact, "sales_contact", lead.contact_id),
    ):
        edge = await _edge_if_exists(
            db,
            relation=entity_type,
            model=model,
            entity_type=entity_type,
            entity_id=fk,
            organization_id=organization_id,
        )
        if edge:
            edges.append(edge)
    return GraphResult(node=_node("sales_lead", lead, "source"), edges=edges)


async def _load_sales_opportunity(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    opportunity = await _get(db, Opportunity, entity_id, organization_id)
    if opportunity is None:
        return None
    edges = []
    account_edge = await _edge_if_exists(
        db,
        relation="account",
        model=Account,
        entity_type="sales_account",
        entity_id=opportunity.account_id,
        organization_id=organization_id,
    )
    if account_edge:
        edges.append(account_edge)
    customer_edge = await _edge_if_exists(
        db,
        relation="onboarded_customer",
        model=Customer,
        entity_type="support_customer",
        entity_id=opportunity.onboarding_customer_id,
        organization_id=organization_id,
    )
    if customer_edge:
        edges.append(customer_edge)
    reviews = await _many(
        db, SecurityReview, opportunity_id=opportunity.id, organization_id=organization_id
    )
    edges += [
        GraphEdge(relation="security_review", node=_node("security_review", r)) for r in reviews
    ]
    return GraphResult(node=_node("sales_opportunity", opportunity), edges=edges)


async def _load_support_customer(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    customer = await _get(db, Customer, entity_id, organization_id)
    if customer is None:
        return None
    edges = []
    account_edge = await _edge_if_exists(
        db,
        relation="sales_account",
        model=Account,
        entity_type="sales_account",
        entity_id=customer.sales_account_id,
        organization_id=organization_id,
    )
    if account_edge:
        edges.append(account_edge)
    tickets = await _many(db, Ticket, customer_id=customer.id, organization_id=organization_id)
    edges += [
        GraphEdge(relation="ticket", node=_node("support_ticket", t, "subject")) for t in tickets
    ]
    return GraphResult(node=_node("support_customer", customer), edges=edges)


async def _load_support_ticket(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    ticket = await _get(db, Ticket, entity_id, organization_id)
    if ticket is None:
        return None
    edges = []
    for model, entity_type, fk in (
        (Customer, "support_customer", ticket.customer_id),
        (SecurityAlert, "security_alert", ticket.related_alert_id),
        (Lead, "sales_lead", ticket.upsell_lead_id),
    ):
        edge = await _edge_if_exists(
            db,
            relation=entity_type,
            model=model,
            entity_type=entity_type,
            entity_id=fk,
            organization_id=organization_id,
        )
        if edge:
            edges.append(edge)
    return GraphResult(node=_node("support_ticket", ticket, "subject"), edges=edges)


async def _load_vendor(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    vendor = await _get(db, Vendor, entity_id, organization_id)
    if vendor is None:
        return None
    assessments = await _many(
        db, VendorAssessment, vendor_id=vendor.id, organization_id=organization_id
    )
    edges = []
    for assessment in assessments:
        risk_edge = await _edge_if_exists(
            db,
            relation="risk",
            model=Risk,
            entity_type="risk",
            entity_id=assessment.related_risk_id,
            organization_id=organization_id,
        )
        if risk_edge:
            edges.append(risk_edge)
    return GraphResult(node=_node("vendor", vendor), edges=edges)


async def _load_risk(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    risk = await _get(db, Risk, entity_id, organization_id)
    if risk is None:
        return None
    edges = []
    control_edge = await _edge_if_exists(
        db,
        relation="control",
        model=Control,
        entity_type="control",
        entity_id=risk.control_id,
        organization_id=organization_id,
    )
    if control_edge:
        edges.append(control_edge)
    return GraphResult(node=_node("risk", risk), edges=edges)


async def _load_control(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    control = await _get(db, Control, entity_id, organization_id)
    if control is None:
        return None
    risks = await _many(db, Risk, control_id=control.id, organization_id=organization_id)
    evidence = await _many(db, Evidence, control_id=control.id, organization_id=organization_id)
    edges = [GraphEdge(relation="risk", node=_node("risk", r)) for r in risks]
    edges += [GraphEdge(relation="evidence", node=_node("evidence", e, "title")) for e in evidence]
    return GraphResult(node=_node("control", control), edges=edges)


async def _load_ai_system(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    system = await _get(db, AISystem, entity_id, organization_id)
    if system is None:
        return None
    dpias = await _many(db, DPIA, ai_system_id=system.id, organization_id=organization_id)
    incidents = await _many(db, AIIncident, ai_system_id=system.id, organization_id=organization_id)
    edges = [GraphEdge(relation="dpia", node=_node("dpia", d)) for d in dpias]
    edges += [GraphEdge(relation="ai_incident", node=_node("ai_incident", i)) for i in incidents]
    return GraphResult(node=_node("ai_system", system), edges=edges)


async def _load_dpia(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    dpia = await _get(db, DPIA, entity_id, organization_id)
    if dpia is None:
        return None
    edges = []
    system_edge = await _edge_if_exists(
        db,
        relation="ai_system",
        model=AISystem,
        entity_type="ai_system",
        entity_id=dpia.ai_system_id,
        organization_id=organization_id,
    )
    if system_edge:
        edges.append(system_edge)
    return GraphResult(node=_node("dpia", dpia), edges=edges)


async def _load_ai_incident(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    incident = await _get(db, AIIncident, entity_id, organization_id)
    if incident is None:
        return None
    edges = []
    for model, entity_type, fk in (
        (AISystem, "ai_system", incident.ai_system_id),
        (Risk, "risk", incident.related_risk_id),
    ):
        edge = await _edge_if_exists(
            db,
            relation=entity_type,
            model=model,
            entity_type=entity_type,
            entity_id=fk,
            organization_id=organization_id,
        )
        if edge:
            edges.append(edge)
    return GraphResult(node=_node("ai_incident", incident), edges=edges)


async def _load_security_asset(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    asset = await _get(db, SecurityAsset, entity_id, organization_id)
    if asset is None:
        return None
    findings = await _many(db, SecurityFinding, asset_id=asset.id, organization_id=organization_id)
    edges = [
        GraphEdge(relation="finding", node=_node("security_finding", f, "title")) for f in findings
    ]
    return GraphResult(node=_node("security_asset", asset), edges=edges)


async def _load_security_finding(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    finding = await _get(db, SecurityFinding, entity_id, organization_id)
    if finding is None:
        return None
    edges = []
    asset_edge = await _edge_if_exists(
        db,
        relation="asset",
        model=SecurityAsset,
        entity_type="security_asset",
        entity_id=finding.asset_id,
        organization_id=organization_id,
    )
    if asset_edge:
        edges.append(asset_edge)
    alerts = await _many(db, SecurityAlert, finding_id=finding.id, organization_id=organization_id)
    edges += [GraphEdge(relation="alert", node=_node("security_alert", a, "title")) for a in alerts]
    return GraphResult(node=_node("security_finding", finding, "title"), edges=edges)


async def _load_security_alert(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    alert = await _get(db, SecurityAlert, entity_id, organization_id)
    if alert is None:
        return None
    edges = []
    finding_edge = await _edge_if_exists(
        db,
        relation="finding",
        model=SecurityFinding,
        entity_type="security_finding",
        entity_id=alert.finding_id,
        organization_id=organization_id,
    )
    if finding_edge:
        edges.append(finding_edge)
    tickets = await _many(db, Ticket, related_alert_id=alert.id, organization_id=organization_id)
    edges += [
        GraphEdge(relation="ticket", node=_node("support_ticket", t, "subject")) for t in tickets
    ]
    return GraphResult(node=_node("security_alert", alert, "title"), edges=edges)


async def _load_security_incident(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    incident = await _get(db, SecurityIncident, entity_id, organization_id)
    if incident is None:
        return None
    edges = []
    risk_edge = await _edge_if_exists(
        db,
        relation="risk",
        model=Risk,
        entity_type="risk",
        entity_id=incident.related_risk_id,
        organization_id=organization_id,
    )
    if risk_edge:
        edges.append(risk_edge)
    return GraphResult(node=_node("security_incident", incident), edges=edges)


async def _load_audit(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    audit = await _get(db, Audit, entity_id, organization_id)
    if audit is None:
        return None
    findings = await _many(db, AuditFinding, audit_id=audit.id, organization_id=organization_id)
    edges = [
        GraphEdge(relation="finding", node=_node("audit_finding", f, "title")) for f in findings
    ]
    return GraphResult(node=_node("audit", audit), edges=edges)


async def _load_security_review(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    review = await _get(db, SecurityReview, entity_id, organization_id)
    if review is None:
        return None
    edges = []
    for model, entity_type, fk in (
        (Opportunity, "sales_opportunity", review.opportunity_id),
        (Questionnaire, "questionnaire", review.questionnaire_id),
    ):
        edge = await _edge_if_exists(
            db,
            relation=entity_type,
            model=model,
            entity_type=entity_type,
            entity_id=fk,
            organization_id=organization_id,
        )
        if edge:
            edges.append(edge)
    return GraphResult(node=_node("security_review", review), edges=edges)


async def _load_questionnaire(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    questionnaire = await _get(db, Questionnaire, entity_id, organization_id)
    if questionnaire is None:
        return None
    edges = []
    opp_edge = await _edge_if_exists(
        db,
        relation="opportunity",
        model=Opportunity,
        entity_type="sales_opportunity",
        entity_id=questionnaire.opportunity_id,
        organization_id=organization_id,
    )
    if opp_edge:
        edges.append(opp_edge)
    return GraphResult(node=_node("questionnaire", questionnaire), edges=edges)


async def _load_data_transfer(
    db: AsyncSession, organization_id: uuid.UUID, entity_id: uuid.UUID
) -> GraphResult | None:
    transfer = await _get(db, DataTransfer, entity_id, organization_id)
    if transfer is None:
        return None
    edges = []
    risk_edge = await _edge_if_exists(
        db,
        relation="risk",
        model=Risk,
        entity_type="risk",
        entity_id=transfer.related_risk_id,
        organization_id=organization_id,
    )
    if risk_edge:
        edges.append(risk_edge)
    return GraphResult(node=_node("data_transfer", transfer, "recipient_name"), edges=edges)


_LOADERS: dict[str, GraphLoader] = {
    "sales_account": _load_sales_account,
    "sales_contact": _load_sales_contact,
    "sales_lead": _load_sales_lead,
    "sales_opportunity": _load_sales_opportunity,
    "support_customer": _load_support_customer,
    "support_ticket": _load_support_ticket,
    "vendor": _load_vendor,
    "risk": _load_risk,
    "control": _load_control,
    "ai_system": _load_ai_system,
    "dpia": _load_dpia,
    "ai_incident": _load_ai_incident,
    "security_asset": _load_security_asset,
    "security_finding": _load_security_finding,
    "security_alert": _load_security_alert,
    "security_incident": _load_security_incident,
    "audit": _load_audit,
    "security_review": _load_security_review,
    "questionnaire": _load_questionnaire,
    "data_transfer": _load_data_transfer,
}

ENTITY_TYPES = sorted(_LOADERS.keys())
