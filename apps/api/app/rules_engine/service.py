"""Business Rules Engine (spec §90). `evaluate_rules` is called from
`app.automation.triggers.dispatch_event` — the exact same real
event-dispatch point Automation workflows already use — so every
existing event source (new vendor, security alert, AI system
registered, ...) automatically evaluates configured Business Rules too,
with no second parallel hook system.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Approval, Membership, MembershipRole, Role
from app.core.notifications import notify
from app.identity.models import User
from app.rules_engine.models import BusinessRule


async def create_business_rule(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    trigger_type: str,
    condition_field: str,
    condition_operator: str,
    condition_value: str,
    action_type: str,
    action_role_key: str,
    action_risk_class: str | None,
) -> BusinessRule:
    rule = BusinessRule(
        organization_id=organization_id,
        name=name,
        trigger_type=trigger_type,
        condition_field=condition_field,
        condition_operator=condition_operator,
        condition_value=condition_value,
        action_type=action_type,
        action_role_key=action_role_key,
        action_risk_class=action_risk_class,
    )
    db.add(rule)
    await db.flush()
    return rule


async def list_business_rules(db: AsyncSession, *, organization_id: uuid.UUID) -> list[BusinessRule]:
    result = await db.execute(
        select(BusinessRule)
        .where(BusinessRule.organization_id == organization_id)
        .order_by(BusinessRule.created_at.desc())
    )
    return list(result.scalars().all())


async def get_org_business_rule(
    db: AsyncSession, *, organization_id: uuid.UUID, rule_id: uuid.UUID
) -> BusinessRule | None:
    rule = await db.get(BusinessRule, rule_id)
    if rule is None or rule.organization_id != organization_id:
        return None
    return rule


async def set_business_rule_active(
    db: AsyncSession, *, organization_id: uuid.UUID, rule_id: uuid.UUID, is_active: bool
) -> BusinessRule | None:
    rule = await get_org_business_rule(db, organization_id=organization_id, rule_id=rule_id)
    if rule is None:
        return None
    rule.is_active = is_active
    await db.flush()
    return rule


async def delete_business_rule(
    db: AsyncSession, *, organization_id: uuid.UUID, rule_id: uuid.UUID
) -> bool:
    rule = await get_org_business_rule(db, organization_id=organization_id, rule_id=rule_id)
    if rule is None:
        return False
    await db.delete(rule)
    await db.flush()
    return True


def _coerce(value: str) -> Any:
    try:
        return float(value)
    except ValueError:
        return value


def _condition_matches(actual: Any, operator: str, expected_raw: str) -> bool:
    actual_coerced = _coerce(str(actual))
    expected_coerced = _coerce(expected_raw)
    try:
        if operator == "==":
            return bool(actual_coerced == expected_coerced)
        if operator == "!=":
            return bool(actual_coerced != expected_coerced)
        # Comparison operators only make sense for real numbers.
        left, right = float(actual_coerced), float(expected_coerced)
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
    except (TypeError, ValueError):
        return False
    return False


async def _users_with_role(db: AsyncSession, *, organization_id: uuid.UUID, role_key: str) -> list[User]:
    result = await db.execute(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(Membership.organization_id == organization_id, Role.key == role_key)
    )
    return list(result.scalars().unique().all())


async def evaluate_rules(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    trigger_type: str,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    result = await db.execute(
        select(BusinessRule).where(
            BusinessRule.organization_id == organization_id,
            BusinessRule.trigger_type == trigger_type,
            BusinessRule.is_active.is_(True),
        )
    )
    rules = list(result.scalars().all())

    for rule in rules:
        if rule.condition_field not in payload:
            continue
        if not _condition_matches(payload[rule.condition_field], rule.condition_operator, rule.condition_value):
            continue

        if rule.action_type == "require_approval" and actor_user_id is not None:
            approval = Approval(
                organization_id=organization_id,
                action_type=f"business_rule:{rule.name}",
                risk_class=rule.action_risk_class or "moderate",
                requested_by=actor_user_id,
            )
            db.add(approval)
            await db.flush()
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="business_rule.approval_required",
                object_type="business_rule",
                object_id=str(rule.id),
                after_state={"approval_id": str(approval.id)},
            )
        elif rule.action_type == "notify":
            users = await _users_with_role(db, organization_id=organization_id, role_key=rule.action_role_key)
            for user in users:
                await notify(
                    db,
                    organization_id=organization_id,
                    user_id=user.id,
                    title=f"Business rule triggered: {rule.name}",
                    body=f"Condition matched: {rule.condition_field} {rule.condition_operator} {rule.condition_value}",
                )
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="business_rule.notified",
                object_type="business_rule",
                object_id=str(rule.id),
                after_state={"notified_user_count": len(users)},
            )
