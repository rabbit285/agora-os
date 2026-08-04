from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.rules_engine.models import BusinessRule
from app.rules_engine.schemas import BusinessRuleCreate, BusinessRuleOut, BusinessRuleUpdate
from app.rules_engine.service import (
    create_business_rule,
    delete_business_rule,
    list_business_rules,
    set_business_rule_active,
)

router = APIRouter(prefix="/api/v1/business-rules", tags=["business-rules"])


@router.get("", response_model=list[BusinessRuleOut])
async def list_organization_business_rules(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[BusinessRule]:
    return await list_business_rules(db, organization_id=context.organization_id)


@router.post("", response_model=BusinessRuleOut, status_code=status.HTTP_201_CREATED)
async def create_organization_business_rule(
    payload: BusinessRuleCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_rules.manage")),
) -> BusinessRule:
    rule = await create_business_rule(
        db,
        organization_id=context.organization_id,
        name=payload.name,
        trigger_type=payload.trigger_type,
        condition_field=payload.condition_field,
        condition_operator=payload.condition_operator,
        condition_value=payload.condition_value,
        action_type=payload.action_type,
        action_role_key=payload.action_role_key,
        action_risk_class=payload.action_risk_class,
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="business_rule.created",
        object_type="business_rule",
        object_id=str(rule.id),
        after_state={"name": rule.name, "trigger_type": rule.trigger_type},
    )
    await db.commit()
    return rule


@router.patch("/{rule_id}", response_model=BusinessRuleOut)
async def update_organization_business_rule(
    rule_id: uuid.UUID,
    payload: BusinessRuleUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_rules.manage")),
) -> BusinessRule:
    rule = await set_business_rule_active(
        db, organization_id=context.organization_id, rule_id=rule_id, is_active=payload.is_active
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business rule not found")
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="business_rule.status_changed",
        object_type="business_rule",
        object_id=str(rule.id),
        after_state={"is_active": rule.is_active},
    )
    await db.commit()
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_organization_business_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_rules.manage")),
) -> None:
    deleted = await delete_business_rule(db, organization_id=context.organization_id, rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business rule not found")
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="business_rule.deleted",
        object_type="business_rule",
        object_id=str(rule_id),
    )
    await db.commit()
