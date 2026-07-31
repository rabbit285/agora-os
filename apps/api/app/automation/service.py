"""Business Process Automation domain services.

`advance_run` is the executor: it runs a `Workflow`'s steps in order,
starting after whatever this `WorkflowRun` has already completed, via the
`STEP_HANDLERS` dispatch table (one entry per supported step type — see
`app.automation.schemas.SUPPORTED_STEP_TYPES` for the full list of 26).
This function itself never touches Temporal — it is invoked from
`run_workflow_step_batch_activity` (apps/worker/worker/activities.py)
running under a real Temporal workflow, and is directly unit-testable on
its own (see tests/test_automation_service.py), the same "activity is a
thin wrapper around a directly-tested function" pattern
`execute_sync_run`/`ingest_document` already established.

`human_approval` is the cross-module hook (spec section 42): it creates a
real `core.Approval` and returns immediately, leaving the run at
`awaiting_approval`. The Temporal workflow driving this run then pauses
on a `wake` signal (see app.automation.workflow_client and
app.routers.approvals) rather than a polling loop — deciding the linked
Approval through the ordinary `/api/v1/approvals/{id}/decide` endpoint
(any module) sends that signal automatically.

`export_data` is the Compliance-as-Governance-Layer cross-module hook
(spec §91: "Automation asks: Can workflow export personal data?").

Credential/scope-gated steps (`send_email`, `send_chat_message`) always
report their real configuration state honestly — never a fabricated
"sent" result — see each handler's docstring.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import GenerateRequest, ModelGateway
from app.audit.service import record_event
from app.automation.models import Workflow, WorkflowRun, WorkflowStepRun, WorkflowVersion
from app.compliance.governance import check_data_export_permission
from app.core.models import Approval, Task
from app.core.notifications import notify
from app.db.base import utcnow

STEP_CREATE_TASK = "create_task"
STEP_SEND_NOTIFICATION = "send_notification"
STEP_HUMAN_APPROVAL = "human_approval"
STEP_EXPORT_DATA = "export_data"
SUPPORTED_STEP_TYPES = {
    "create_task",
    "send_notification",
    "human_approval",
    "export_data",
    "create_record",
    "update_record",
    "send_email",
    "send_chat_message",
    "assign_user",
    "generate_document",
    "analyze_document",
    "extract_data",
    "classify_data",
    "call_api",
    "webhook",
    "search_knowledge",
    "generate_ai_response",
    "run_compliance_assessment",
    "run_security_check",
    "create_lead",
    "update_crm",
    "create_support_ticket",
    "create_report",
    "delay",
    "condition",
    "loop",
}


@dataclass
class StepContext:
    db: AsyncSession
    run: WorkflowRun
    workflow: Workflow
    step_index: int
    config: dict[str, Any]
    actor_user_id: uuid.UUID | None


def _step_run(
    ctx: StepContext,
    step_type: str,
    status: str,
    output: dict[str, Any] | None = None,
    approval_id: uuid.UUID | None = None,
) -> WorkflowStepRun:
    return WorkflowStepRun(
        organization_id=ctx.run.organization_id,
        run_id=ctx.run.id,
        step_index=ctx.step_index,
        step_type=step_type,
        status=status,
        output=output,
        approval_id=approval_id,
    )


async def _handle_create_task(ctx: StepContext) -> WorkflowStepRun:
    task = Task(
        organization_id=ctx.run.organization_id,
        title=ctx.config.get("title", "Automation task"),
        description=ctx.config.get("description"),
        module="automation",
        priority=ctx.config.get("priority", "normal"),
    )
    ctx.db.add(task)
    await ctx.db.flush()
    return _step_run(ctx, STEP_CREATE_TASK, "succeeded", {"task_id": str(task.id)})


async def _handle_send_notification(ctx: StepContext) -> WorkflowStepRun:
    recipient_id = ctx.actor_user_id or ctx.run.triggered_by
    if recipient_id is None:
        return _step_run(
            ctx,
            STEP_SEND_NOTIFICATION,
            "failed",
            {"reason": "No user to notify (unattributed run, e.g. a webhook/schedule trigger)"},
        )
    notification = await notify(
        ctx.db,
        organization_id=ctx.run.organization_id,
        user_id=recipient_id,
        title=ctx.config.get("title", "Workflow notification"),
        body=ctx.config.get("body"),
    )
    return _step_run(
        ctx, STEP_SEND_NOTIFICATION, "succeeded", {"notification_id": str(notification.id)}
    )


async def _handle_human_approval(ctx: StepContext) -> WorkflowStepRun:
    approval = Approval(
        organization_id=ctx.run.organization_id,
        action_type=ctx.config.get("action_type", f"Workflow approval: {ctx.workflow.name}"),
        risk_class=ctx.config.get("risk_class", "moderate"),
        requested_by=ctx.run.triggered_by or ctx.actor_user_id,
    )
    ctx.db.add(approval)
    await ctx.db.flush()
    ctx.run.status = "awaiting_approval"
    return _step_run(ctx, STEP_HUMAN_APPROVAL, "awaiting_approval", approval_id=approval.id)


async def _handle_export_data(ctx: StepContext) -> WorkflowStepRun:
    decision = await check_data_export_permission(
        ctx.db,
        organization_id=ctx.run.organization_id,
        destination_country=ctx.config.get("destination_country", ""),
        data_classification=ctx.config.get("data_classification", "internal"),
    )
    if not decision.allowed:
        ctx.run.status = "failed"
    return _step_run(
        ctx,
        STEP_EXPORT_DATA,
        "succeeded" if decision.allowed else "failed",
        {"allowed": decision.allowed, "reason": decision.reason},
    )


_CREATE_RECORD_ENTITIES = {"security_asset", "compliance_risk", "sales_account", "support_customer"}


async def _handle_create_record(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Create record" — a small, disclosed set of entities not
    already covered by their own dedicated action (create_lead,
    create_support_ticket)."""
    entity_type = ctx.config.get("entity_type")
    fields = ctx.config.get("fields") or {}
    if entity_type not in _CREATE_RECORD_ENTITIES:
        return _step_run(
            ctx,
            "create_record",
            "failed",
            {"reason": f"Unsupported entity_type: {entity_type}"},
        )

    record: Any
    if entity_type == "security_asset":
        from app.secops.models import SecurityAsset

        record = SecurityAsset(organization_id=ctx.run.organization_id, **fields)
    elif entity_type == "compliance_risk":
        from app.compliance.models import Risk

        record = Risk(organization_id=ctx.run.organization_id, **fields)
    elif entity_type == "sales_account":
        from app.sales.models import Account

        record = Account(organization_id=ctx.run.organization_id, **fields)
    else:
        from app.support.models import Customer

        record = Customer(organization_id=ctx.run.organization_id, **fields)

    ctx.db.add(record)
    await ctx.db.flush()
    return _step_run(
        ctx, "create_record", "succeeded", {"entity_type": entity_type, "entity_id": str(record.id)}
    )


_UPDATE_RECORD_MODELS: dict[str, tuple[str, str]] = {
    "security_asset": ("app.secops.models", "SecurityAsset"),
    "compliance_risk": ("app.compliance.models", "Risk"),
    "sales_account": ("app.sales.models", "Account"),
    "support_customer": ("app.support.models", "Customer"),
}


async def _handle_update_record(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Update record" — bounded to updating `status` on the
    same small entity set `create_record` covers, to keep this a real,
    safe, generic action rather than an unbounded field-injection API."""
    entity_type = ctx.config.get("entity_type")
    entity_id = ctx.config.get("entity_id")
    new_status = ctx.config.get("status")
    if entity_type not in _UPDATE_RECORD_MODELS or not entity_id or not new_status:
        return _step_run(
            ctx,
            "update_record",
            "failed",
            {"reason": "entity_type, entity_id, and status are all required"},
        )

    import importlib

    module_name, class_name = _UPDATE_RECORD_MODELS[entity_type]
    model_cls = getattr(importlib.import_module(module_name), class_name)
    record = await ctx.db.get(model_cls, uuid.UUID(entity_id))
    if record is None or record.organization_id != ctx.run.organization_id:
        return _step_run(ctx, "update_record", "failed", {"reason": "Record not found"})

    record.status = new_status
    return _step_run(
        ctx, "update_record", "succeeded", {"entity_type": entity_type, "status": new_status}
    )


async def _handle_send_email(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Send email" — this build has no real SMTP/SES dispatch
    path anywhere yet (see docs/KNOWN_LIMITATIONS.md); logs the intended
    send and honestly reports it was never actually delivered, the same
    pattern app.identity.service._dispatch_password_reset_email uses."""
    import logging

    logger = logging.getLogger("agora.automation")
    to = ctx.config.get("to", "(unspecified)")
    subject = ctx.config.get("subject", "(no subject)")
    logger.info(
        "Automation send_email step (not delivered, no SMTP provider): to=%s subject=%s",
        to,
        subject,
    )
    return _step_run(
        ctx,
        "send_email",
        "succeeded",
        {"sent": False, "reason": "No SMTP/SES provider configured in this build", "to": to},
    )


async def _handle_send_chat_message(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Send Slack/Teams message" — this build's Slack/Microsoft
    OAuth connectors are deliberately scoped read-only
    (`channels:read` only, Stage 1 progressive trust model — see
    app.integrations.adapters.slack) and cannot post messages. Always
    honestly reports this rather than attempting a call guaranteed to
    fail on scope, or fabricating a "sent" result."""
    from app.integrations.models import IntegrationConnection

    result = await ctx.db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == ctx.run.organization_id,
            IntegrationConnection.connector_key.in_(["slack", "microsoft"]),
            IntegrationConnection.status == "connected",
        )
    )
    connection = result.scalars().first()
    reason = (
        "Slack/Microsoft Teams connections in this build are read-only "
        "(channels:read scope only) — posting requires a broader OAuth scope "
        "not requested in this build's Stage 1 progressive trust model."
        if connection is not None
        else "No Slack or Microsoft Teams connection configured for this organization."
    )
    return _step_run(
        ctx,
        "send_chat_message",
        "succeeded",
        {"sent": False, "connection_found": connection is not None, "reason": reason},
    )


async def _handle_assign_user(ctx: StepContext) -> WorkflowStepRun:
    entity_type = ctx.config.get("entity_type")
    entity_id = ctx.config.get("entity_id")
    user_id = ctx.config.get("user_id")
    if entity_type != "task" or not entity_id or not user_id:
        return _step_run(
            ctx,
            "assign_user",
            "failed",
            {"reason": "entity_type must be 'task' with entity_id/user_id"},
        )
    task = await ctx.db.get(Task, uuid.UUID(entity_id))
    if task is None or task.organization_id != ctx.run.organization_id:
        return _step_run(ctx, "assign_user", "failed", {"reason": "Task not found"})
    task.assignee_id = uuid.UUID(user_id)
    return _step_run(ctx, "assign_user", "succeeded", {"task_id": entity_id, "user_id": user_id})


async def _handle_generate_document(ctx: StepContext) -> WorkflowStepRun:
    """Generates real text via the AI Gateway (grounded prompt from
    config) and stores it as a real core.File — not a placeholder
    document. Requires a real triggering user (File.uploaded_by is
    NOT NULL); a run with no user context (e.g. an unattributed webhook
    trigger) honestly reports it can't attribute a File owner rather
    than fabricating one."""
    uploader_id = ctx.actor_user_id or ctx.run.triggered_by
    if uploader_id is None:
        return _step_run(
            ctx,
            "generate_document",
            "failed",
            {"reason": "No user to attribute the generated File to"},
        )

    from app.core.storage import upload_object

    gateway = ModelGateway()
    prompt = ctx.config.get("prompt", "Generate a short document.")
    result = await gateway.generate(
        ctx.db,
        organization_id=ctx.run.organization_id,
        requested_by=ctx.actor_user_id,
        request=GenerateRequest(task_type="automation.generate_document", prompt=prompt),
    )
    body = result.text.encode("utf-8")
    storage_key = f"automation-generated/{uuid.uuid4()}.txt"
    upload_object(storage_key, body, content_type="text/plain")

    from app.core.models import File

    file_record = File(
        organization_id=ctx.run.organization_id,
        original_filename=ctx.config.get("filename", "generated-document.txt"),
        content_type="text/plain",
        size_bytes=len(body),
        storage_key=storage_key,
        uploaded_by=uploader_id,
    )
    ctx.db.add(file_record)
    await ctx.db.flush()
    return _step_run(
        ctx,
        "generate_document",
        "succeeded",
        {"file_id": str(file_record.id), "provider": result.provider},
    )


async def _handle_analyze_document(ctx: StepContext) -> WorkflowStepRun:
    """Real retrieval-grounded analysis via the existing AI Copilot."""
    from app.ai.copilot import ask_copilot

    question = ctx.config.get("question", "Summarize the key points of the referenced document.")
    answer = await ask_copilot(
        ctx.db,
        organization_id=ctx.run.organization_id,
        requested_by=ctx.actor_user_id,
        question=question,
    )
    return _step_run(
        ctx, "analyze_document", "succeeded", {"analysis": answer.text, "grounded": answer.grounded}
    )


async def _generate_json(ctx: StepContext, prompt: str) -> dict[str, Any]:
    gateway = ModelGateway()
    result = await gateway.generate(
        ctx.db,
        organization_id=ctx.run.organization_id,
        requested_by=ctx.actor_user_id,
        request=GenerateRequest(task_type="automation.structured_output", prompt=prompt),
    )
    try:
        return dict(json.loads(result.text))
    except (json.JSONDecodeError, ValueError):
        return {"raw_text": result.text}


async def _handle_extract_data(ctx: StepContext) -> WorkflowStepRun:
    text = ctx.config.get("text", "")
    fields = ctx.config.get("fields", [])
    prompt = (
        f"Extract the following fields as a JSON object with exactly these keys: "
        f"{fields}. Respond with ONLY the JSON object, no other text.\n\nText:\n{text}"
    )
    extracted = await _generate_json(ctx, prompt)
    return _step_run(ctx, "extract_data", "succeeded", {"extracted": extracted})


async def _handle_classify_data(ctx: StepContext) -> WorkflowStepRun:
    text = ctx.config.get("text", "")
    labels = ctx.config.get("labels", [])
    prompt = (
        f"Classify the following text as exactly one of these labels: {labels}. "
        f"Respond with ONLY the chosen label, no other text.\n\nText:\n{text}"
    )
    gateway = ModelGateway()
    result = await gateway.generate(
        ctx.db,
        organization_id=ctx.run.organization_id,
        requested_by=ctx.actor_user_id,
        request=GenerateRequest(task_type="automation.classify_data", prompt=prompt),
    )
    label = result.text.strip()
    matched = next(
        (label_option for label_option in labels if label_option.lower() in label.lower()), None
    )
    return _step_run(
        ctx, "classify_data", "succeeded", {"label": matched or label, "raw_response": result.text}
    )


async def _handle_call_api(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Call API" — a real outbound HTTP call, response captured
    in the step's output."""
    url = ctx.config.get("url")
    if not url:
        return _step_run(ctx, "call_api", "failed", {"reason": "config.url is required"})
    method = ctx.config.get("method", "GET").upper()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method, url, json=ctx.config.get("body"), headers=ctx.config.get("headers")
            )
    except httpx.HTTPError as exc:
        return _step_run(ctx, "call_api", "failed", {"reason": str(exc)})
    return _step_run(
        ctx,
        "call_api",
        "succeeded" if response.status_code < 400 else "failed",
        {"status_code": response.status_code, "body": response.text[:2000]},
    )


async def _handle_webhook(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Webhook" (action) — fire-and-forget outbound POST,
    distinct from the Webhook *trigger* (an inbound receiver)."""
    url = ctx.config.get("url")
    if not url:
        return _step_run(ctx, "webhook", "failed", {"reason": "config.url is required"})
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=ctx.run.trigger_payload or {})
    except httpx.HTTPError as exc:
        return _step_run(ctx, "webhook", "failed", {"reason": str(exc)})
    return _step_run(ctx, "webhook", "succeeded", {"status_code": response.status_code})


async def _handle_search_knowledge(ctx: StepContext) -> WorkflowStepRun:
    from app.search.service import global_search

    query = ctx.config.get("query", "")
    results = await global_search(ctx.db, organization_id=ctx.run.organization_id, query=query)
    return _step_run(
        ctx,
        "search_knowledge",
        "succeeded",
        {"result_count": len(results), "results": [r.__dict__ for r in results[:10]]},
    )


async def _handle_generate_ai_response(ctx: StepContext) -> WorkflowStepRun:
    from app.ai.copilot import ask_copilot

    question = ctx.config.get("question", "")
    answer = await ask_copilot(
        ctx.db,
        organization_id=ctx.run.organization_id,
        requested_by=ctx.actor_user_id,
        question=question,
    )
    return _step_run(
        ctx,
        "generate_ai_response",
        "succeeded",
        {"answer": answer.text, "grounded": answer.grounded},
    )


async def _handle_run_compliance_assessment(ctx: StepContext) -> WorkflowStepRun:
    from app.compliance.models import Control
    from app.compliance.service import record_assessment

    control_id = ctx.config.get("control_id")
    if not control_id:
        return _step_run(
            ctx, "run_compliance_assessment", "failed", {"reason": "config.control_id is required"}
        )
    control = await ctx.db.get(Control, uuid.UUID(control_id))
    if control is None or control.organization_id != ctx.run.organization_id:
        return _step_run(
            ctx, "run_compliance_assessment", "failed", {"reason": "Control not found"}
        )
    assessment = await record_assessment(
        ctx.db,
        organization_id=ctx.run.organization_id,
        control=control,
        status=ctx.config.get("status", "not_assessed"),
        notes=ctx.config.get("notes"),
        assessed_by=ctx.actor_user_id,
    )
    return _step_run(
        ctx, "run_compliance_assessment", "succeeded", {"assessment_id": str(assessment.id)}
    )


async def _handle_run_security_check(ctx: StepContext) -> WorkflowStepRun:
    from app.secops.cloud_scanner import run_cloud_security_scan

    result = await run_cloud_security_scan(
        ctx.db, organization_id=ctx.run.organization_id, actor_user_id=ctx.actor_user_id
    )
    return _step_run(
        ctx,
        "run_security_check",
        "succeeded",
        {"configured": result.configured, "findings_created": result.findings_created},
    )


async def _handle_create_lead(ctx: StepContext) -> WorkflowStepRun:
    from app.sales.models import Lead

    lead = Lead(
        organization_id=ctx.run.organization_id,
        account_id=uuid.UUID(ctx.config["account_id"]) if ctx.config.get("account_id") else None,
        source=ctx.config.get("source", "automation"),
    )
    ctx.db.add(lead)
    await ctx.db.flush()
    return _step_run(ctx, "create_lead", "succeeded", {"lead_id": str(lead.id)})


_UPDATE_CRM_MODELS: dict[str, tuple[str, str, str]] = {
    "sales_account": ("app.sales.models", "Account", "status"),
    "sales_opportunity": ("app.sales.models", "Opportunity", "stage"),
    "sales_lead": ("app.sales.models", "Lead", "status"),
}


async def _handle_update_crm(ctx: StepContext) -> WorkflowStepRun:
    entity_type = ctx.config.get("entity_type")
    entity_id = ctx.config.get("entity_id")
    value = ctx.config.get("value")
    if entity_type not in _UPDATE_CRM_MODELS or not entity_id or not value:
        return _step_run(
            ctx,
            "update_crm",
            "failed",
            {"reason": "entity_type, entity_id, and value are all required"},
        )
    import importlib

    module_name, class_name, field_name = _UPDATE_CRM_MODELS[entity_type]
    model_cls = getattr(importlib.import_module(module_name), class_name)
    record = await ctx.db.get(model_cls, uuid.UUID(entity_id))
    if record is None or record.organization_id != ctx.run.organization_id:
        return _step_run(ctx, "update_crm", "failed", {"reason": "Record not found"})
    setattr(record, field_name, value)
    return _step_run(
        ctx, "update_crm", "succeeded", {"entity_type": entity_type, field_name: value}
    )


async def _handle_create_support_ticket(ctx: StepContext) -> WorkflowStepRun:
    from app.support.service import create_ticket

    customer_id = ctx.config.get("customer_id")
    if not customer_id:
        return _step_run(
            ctx, "create_support_ticket", "failed", {"reason": "config.customer_id is required"}
        )
    ticket = await create_ticket(
        ctx.db,
        organization_id=ctx.run.organization_id,
        customer_id=uuid.UUID(customer_id),
        subject=ctx.config.get("subject", "Automation-created ticket"),
        description=ctx.config.get("description"),
        channel="api",
        category=ctx.config.get("category", "general"),
        priority=ctx.config.get("priority", "medium"),
        actor_user_id=ctx.actor_user_id,
    )
    return _step_run(ctx, "create_support_ticket", "succeeded", {"ticket_id": str(ticket.id)})


async def _handle_create_report(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Create report" — a real aggregate snapshot from the same
    live-computed dashboards Sales/Support/Security already expose,
    stored as this run's step output (not a fabricated document)."""
    report_type = ctx.config.get("report_type", "sales_intelligence")
    if report_type == "sales_intelligence":
        from app.sales.intelligence import compute_sales_intelligence

        data = await compute_sales_intelligence(ctx.db, organization_id=ctx.run.organization_id)
        data["top_accounts_by_icp_score"] = [
            a.id and str(a.id) for a in data["top_accounts_by_icp_score"]
        ]
    elif report_type == "support_analytics":
        from app.support.analytics import compute_support_analytics

        data = await compute_support_analytics(ctx.db, organization_id=ctx.run.organization_id)
    else:
        return _step_run(
            ctx, "create_report", "failed", {"reason": f"Unsupported report_type: {report_type}"}
        )
    return _step_run(ctx, "create_report", "succeeded", {"report_type": report_type, "data": data})


async def _handle_delay(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Wait" — a real durable sleep under Temporal
    (workflow.sleep, see apps/worker/worker/workflows.py); this handler
    only records that the wait occurred, since the sleep itself happens
    in the workflow, not the activity."""
    seconds = ctx.config.get("seconds", 0)
    return _step_run(ctx, "delay", "succeeded", {"waited_seconds": seconds})


_CONDITION_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "equals": lambda a, b: bool(a == b),
    "not_equals": lambda a, b: bool(a != b),
    "contains": lambda a, b: b in a if isinstance(a, str) else False,
}


async def _handle_condition(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Branch" — evaluates a simple condition against this
    run's trigger_payload; a false result ends the run successfully
    (skipping remaining steps) rather than failing it, since "the
    condition wasn't met" is not an error."""
    field = ctx.config.get("field")
    operator = str(ctx.config.get("operator", "equals"))
    expected = ctx.config.get("value")
    payload = ctx.run.trigger_payload or {}
    actual = payload.get(field) if field else None
    operator_fn = _CONDITION_OPERATORS.get(operator, _CONDITION_OPERATORS["equals"])
    matched = operator_fn(actual, expected)
    if not matched:
        ctx.run.status = "succeeded"
        ctx.run.completed_at = utcnow()
    return _step_run(ctx, "condition", "succeeded", {"matched": matched, "actual": actual})


async def _handle_loop(ctx: StepContext) -> WorkflowStepRun:
    """spec §39 "Loop" — repeats one nested step once per item in
    config.items (a literal list, or a trigger_payload field name). A
    bounded v1: one repeated step type, not an arbitrary nested step
    tree."""
    items = ctx.config.get("items")
    if isinstance(items, str):
        items = (ctx.run.trigger_payload or {}).get(items, [])
    items = items or []
    inner_step_type = str(ctx.config.get("step_type", ""))
    inner_config_template = ctx.config.get("config") or {}

    handler = STEP_HANDLERS.get(inner_step_type)
    if handler is None:
        return _step_run(
            ctx, "loop", "failed", {"reason": f"Unsupported inner step_type: {inner_step_type}"}
        )

    results = []
    for item in items:
        inner_config = {**inner_config_template, "item": item}
        inner_ctx = StepContext(
            db=ctx.db,
            run=ctx.run,
            workflow=ctx.workflow,
            step_index=ctx.step_index,
            config=inner_config,
            actor_user_id=ctx.actor_user_id,
        )
        inner_result = await handler(inner_ctx)
        results.append(inner_result.output)

    return _step_run(ctx, "loop", "succeeded", {"iterations": len(items), "results": results})


STEP_HANDLERS: dict[str, Any] = {
    "create_task": _handle_create_task,
    "send_notification": _handle_send_notification,
    "human_approval": _handle_human_approval,
    "export_data": _handle_export_data,
    "create_record": _handle_create_record,
    "update_record": _handle_update_record,
    "send_email": _handle_send_email,
    "send_chat_message": _handle_send_chat_message,
    "assign_user": _handle_assign_user,
    "generate_document": _handle_generate_document,
    "analyze_document": _handle_analyze_document,
    "extract_data": _handle_extract_data,
    "classify_data": _handle_classify_data,
    "call_api": _handle_call_api,
    "webhook": _handle_webhook,
    "search_knowledge": _handle_search_knowledge,
    "generate_ai_response": _handle_generate_ai_response,
    "run_compliance_assessment": _handle_run_compliance_assessment,
    "run_security_check": _handle_run_security_check,
    "create_lead": _handle_create_lead,
    "update_crm": _handle_update_crm,
    "create_support_ticket": _handle_create_support_ticket,
    "create_report": _handle_create_report,
    "delay": _handle_delay,
    "condition": _handle_condition,
    "loop": _handle_loop,
}


async def start_run(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    workflow: Workflow,
    trigger_payload: dict[str, Any] | None,
    actor_user_id: uuid.UUID | None,
) -> WorkflowRun:
    """Creates the `WorkflowRun` row and returns immediately — execution
    is kicked off separately by the caller via
    `app.automation.workflow_client.start_workflow_run` (spec §61: never
    couple workflow execution to the HTTP request)."""
    run = WorkflowRun(
        organization_id=organization_id,
        workflow_id=workflow.id,
        status="running",
        trigger_payload=trigger_payload,
        triggered_by=actor_user_id,
        started_at=utcnow(),
    )
    db.add(run)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="automation.run.started",
        object_type="automation_workflow_run",
        object_id=str(run.id),
        after_state={"workflow_id": str(workflow.id)},
    )
    return run


async def advance_run(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    workflow: Workflow,
    actor_user_id: uuid.UUID | None,
) -> WorkflowRun:
    if run.status not in ("running", "awaiting_approval"):
        return run

    existing = (
        (
            await db.execute(
                select(WorkflowStepRun)
                .where(WorkflowStepRun.run_id == run.id)
                .order_by(WorkflowStepRun.step_index)
            )
        )
        .scalars()
        .all()
    )
    step_runs = list(existing)
    next_index = len(step_runs)

    if step_runs and step_runs[-1].status == "awaiting_approval":
        pending_step = step_runs[-1]
        approval = await db.get(Approval, pending_step.approval_id)
        assert approval is not None  # FK guarantees existence
        if approval.status == "pending":
            return run
        if approval.status == "rejected":
            pending_step.status = "failed"
            run.status = "failed"
            run.completed_at = utcnow()
            await record_event(
                db,
                organization_id=run.organization_id,
                actor_user_id=actor_user_id,
                action="automation.run.failed",
                object_type="automation_workflow_run",
                object_id=str(run.id),
                after_state={"reason": "human_approval step rejected"},
            )
            return run
        pending_step.status = "succeeded"
        run.status = "running"

    for index in range(next_index, len(workflow.steps)):
        step = workflow.steps[index]
        step_type = step["step_type"]
        config = step.get("config") or {}
        handler = STEP_HANDLERS.get(step_type)
        if handler is None:
            raise ValueError(f"Unsupported step type: {step_type}")

        ctx = StepContext(
            db=db,
            run=run,
            workflow=workflow,
            step_index=index,
            config=config,
            actor_user_id=actor_user_id,
        )
        step_run = await handler(ctx)
        db.add(step_run)
        await db.flush()

        if run.status == "awaiting_approval":
            await record_event(
                db,
                organization_id=run.organization_id,
                actor_user_id=actor_user_id,
                action="automation.run.awaiting_approval",
                object_type="automation_workflow_run",
                object_id=str(run.id),
                after_state={"approval_id": str(step_run.approval_id)},
            )
            return run
        if run.status == "failed":
            await record_event(
                db,
                organization_id=run.organization_id,
                actor_user_id=actor_user_id,
                action="automation.run.failed",
                object_type="automation_workflow_run",
                object_id=str(run.id),
                policy_decision="denied",
                after_state=step_run.output,
            )
            run.completed_at = utcnow()
            return run
        if run.status == "succeeded" and run.completed_at is not None:
            # A condition step ended the run early (its own branch-false path).
            await record_event(
                db,
                organization_id=run.organization_id,
                actor_user_id=actor_user_id,
                action="automation.run.succeeded",
                object_type="automation_workflow_run",
                object_id=str(run.id),
                after_state={"status": run.status, "ended_early_at_step": index},
            )
            return run
        if step_type == "delay":
            # Real durable waiting happens one level up, in the Temporal
            # workflow (workflow.sleep) — see apps/worker/worker/workflows.py
            # and run_workflow_step_batch_activity. Returning here lets that
            # workflow read `output["waited_seconds"]` off this step_run and
            # sleep for real before resuming at the next index.
            return run

    run.status = "succeeded"
    run.completed_at = utcnow()
    await record_event(
        db,
        organization_id=run.organization_id,
        actor_user_id=actor_user_id,
        action="automation.run.succeeded",
        object_type="automation_workflow_run",
        object_id=str(run.id),
        after_state={"status": run.status},
    )
    return run


async def publish_workflow_version(
    db: AsyncSession, *, workflow: Workflow, published_by: uuid.UUID | None
) -> WorkflowVersion:
    """spec §41 versioning: snapshots `Workflow.steps` immutably. Called
    whenever a workflow transitions into `active` — see
    app.routers.automation.update_workflow_status."""
    version = WorkflowVersion(
        organization_id=workflow.organization_id,
        workflow_id=workflow.id,
        version_number=workflow.version,
        steps=workflow.steps,
        trigger_type=workflow.trigger_type,
        published_by=published_by,
    )
    db.add(version)
    await db.flush()
    return version
