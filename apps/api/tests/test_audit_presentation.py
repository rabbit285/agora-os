"""The audit trail, read by a person rather than a debugger.

The screen was showing the stored row: `compliance.control.assessed`,
`after {"status":"pass"}`, and a bare UUID. Everything a compliance
manager needs from it — what changed, to what, by whom, and why — was in
the database and absent from the page.

These tests hold both halves. The timeline says it in words and carries
no identifier a reader cannot use; the raw event survives underneath,
because an auditor tracing one record needs exactly the fields a normal
reader must never be shown by default.
"""

from __future__ import annotations

import re
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.presentation import (
    TITLES,
    actor_kind_for,
    build_views,
    category_for,
    format_value,
    reason_from,
    summarize_change,
)
from app.audit.service import record_event
from app.compliance.models import ComplianceGap, Control, Framework, Policy, Requirement
from app.core.routes import RETIRED_ROUTE_PREFIXES

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _control(db: AsyncSession, org_id: uuid.UUID, title: str) -> Control:
    control = Control(organization_id=org_id, title=title, description=None)
    db.add(control)
    await db.flush()
    return control


# --- A. a human review ------------------------------------------------


async def test_a_human_review_reads_as_a_sentence_with_a_before_and_after(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "audit-human@example.com", "Audit Human Org")
    control = await _control(db_session, org_id, "Monitor AI systems in production")

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=user_id,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(control.id),
        before_state={"status": "needs_review"},
        after_state={
            "status": "pass",
            "notes": "Reviewed operational monitoring evidence and confirmed it is sufficient.",
        },
    )
    await db_session.commit()

    response = await client.get("/api/v1/audit-events", params={"limit": 20})
    assert response.status_code == 200, response.text
    event = next(
        item for item in response.json() if item["action"] == "compliance.control.assessed"
    )

    assert event["title"] == "Control assessment recorded"
    assert event["entity"]["label"] == "Monitor AI systems in production"
    assert event["entity"]["kind"] == "Control"
    assert event["entity"]["href"] == f"/compliance/controls/{control.id}"

    # The change, as an arrow rather than as JSON.
    change = next(c for c in event["changes"] if c["label"] == "Status")
    assert change["before"] == "Needs review"
    assert change["after"] == "Passed"

    # Who, and why.
    assert event["actor_kind"] == "person"
    assert event["actor_name"] == "Zach W."
    assert event["reason"].startswith("Reviewed operational monitoring evidence")


# --- B, C. the other two shapes in the screenshot ---------------------


async def test_a_framework_reassessment_names_the_framework_and_its_counts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "audit-fw@example.com", "Audit Framework Org")
    framework = Framework(key=f"iso-{uuid.uuid4().hex[:6]}", name="ISO 42001", description=None)
    db_session.add(framework)
    await db_session.flush()

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=user_id,
        action="compliance.framework.assessed",
        object_type="framework",
        object_id=str(framework.id),
        after_state={
            "requirements_evaluated": 18,
            "satisfied": 2,
            "needs_review": 13,
            "gaps": 3,
        },
    )
    await db_session.commit()

    response = await client.get("/api/v1/audit-events", params={"limit": 20})
    event = next(
        item for item in response.json() if item["action"] == "compliance.framework.assessed"
    )

    assert event["title"] == "Framework reassessed"
    assert event["entity"]["label"] == "ISO 42001"
    assert event["entity"]["href"] == f"/compliance/frameworks/{framework.id}"

    readable = {c["label"]: c["after"] for c in event["changes"]}
    assert readable["Requirements evaluated"] == "18"
    assert readable["Satisfied"] == "2"
    assert readable["Awaiting review"] == "13"
    assert readable["Gaps"] == "3"


async def test_a_remediation_update_names_the_gap_and_its_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "audit-gap@example.com", "Audit Gap Org")
    framework = Framework(key=f"gdpr-{uuid.uuid4().hex[:6]}", name="GDPR", description=None)
    db_session.add(framework)
    await db_session.flush()
    requirement = Requirement(
        framework_id=framework.id, reference_code="Art. 4", title="AI literacy", description=None
    )
    db_session.add(requirement)
    await db_session.flush()
    gap = ComplianceGap(
        organization_id=org_id,
        framework_id=framework.id,
        requirement_id=requirement.id,
        kind="requirement_uncovered",
        summary="AI literacy training evidence incomplete",
        severity="medium",
        status="open",
    )
    db_session.add(gap)
    await db_session.flush()

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        action="compliance.gap.remediation_updated",
        object_type="compliance_gap",
        object_id=str(gap.id),
        after_state={
            "requirement": "5.2",
            "owner": "Management",
            "checklist_items": 5,
            "required_evidence": 3,
            "evidence_reviewed": 1,
        },
    )
    await db_session.commit()

    response = await client.get("/api/v1/audit-events", params={"limit": 20})
    event = next(
        item
        for item in response.json()
        if item["action"] == "compliance.gap.remediation_updated"
    )

    assert event["title"] == "Remediation plan updated"
    assert event["entity"]["label"] == "AI literacy training evidence incomplete"
    # A gap is read on the framework screen, beside the requirement it is
    # about — it has no page of its own to link to.
    assert event["entity"]["href"] == f"/compliance/frameworks/{framework.id}"

    readable = {c["label"]: c["after"] for c in event["changes"]}
    assert readable["Owner"] == "Management"
    assert readable["Checklist"] == "5"
    assert readable["Required evidence"] == "3"
    assert readable["Evidence reviewed"] == "1"


# --- D, E. who did it -------------------------------------------------


def test_an_action_a_model_performed_is_attributed_to_veyntra_ai() -> None:
    assert actor_kind_for("compliance.gap.remediation_generated", has_user=True) == "ai"
    assert actor_kind_for("compliance.policy.detected", has_user=False) == "ai"
    assert actor_kind_for("compliance.evidence.suggestion_auto_approved", True) == "ai"


def test_an_action_the_rules_performed_is_attributed_to_the_system() -> None:
    # Assessment in this product is deterministic rules over declared
    # facts, never a model call. Calling it AI would misrepresent how the
    # number was reached, so it is System even though a person pressed
    # the button that triggered it.
    assert actor_kind_for("compliance.framework.assessed", has_user=True) == "system"
    assert actor_kind_for("compliance.gap.created", has_user=True) == "system"


def test_an_event_with_no_recorded_actor_says_so_rather_than_inventing_one() -> None:
    assert actor_kind_for("auth.login", has_user=False) == "unknown"
    assert actor_kind_for("integrations.webhook.received", has_user=False) == "integration"


async def test_veyntra_ai_and_system_are_named_on_the_card(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "audit-actors@example.com", "Audit Actors Org")
    framework = Framework(key=f"soc-{uuid.uuid4().hex[:6]}", name="SOC 2", description=None)
    db_session.add(framework)
    await db_session.flush()

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        action="compliance.framework.assessed",
        object_type="framework",
        object_id=str(framework.id),
        after_state={"requirements_evaluated": 2, "satisfied": 0},
    )
    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        action="compliance.policy.detected",
        object_type="framework",
        object_id=str(framework.id),
        after_state={"title": "AI Governance Policy"},
    )
    await db_session.commit()

    body = (await client.get("/api/v1/audit-events", params={"limit": 20})).json()
    by_action = {item["action"]: item for item in body}
    assert by_action["compliance.framework.assessed"]["actor_name"] == "Veyntra System"
    assert by_action["compliance.policy.detected"]["actor_name"] == "Veyntra AI"


# --- the headline requirement: nothing raw on the card ----------------


async def test_no_identifier_or_json_appears_in_anything_the_reader_sees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A real event carries `control_id`, `evidence_id` and friends in its
    after-state. Rendering those put a UUID back on the timeline through
    the side door, which is the thing this redesign exists to stop."""
    user_id, org_id = await _signup(client, "audit-raw@example.com", "Audit Raw Org")
    control = await _control(db_session, org_id, "Encrypt data at rest")

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=user_id,
        action="compliance.evidence.suggestion_auto_approved",
        object_type="control",
        object_id=str(control.id),
        after_state={
            "control_id": str(control.id),
            "evidence_id": str(uuid.uuid4()),
            "confidence": 0.97,
            "checklist": [{"text": "Step one", "done": True}, {"text": "Step two", "done": False}],
        },
    )
    await db_session.commit()

    body = (await client.get("/api/v1/audit-events", params={"limit": 20})).json()
    event = next(
        item
        for item in body
        if item["action"] == "compliance.evidence.suggestion_auto_approved"
    )

    visible = [
        event["title"],
        event["actor_name"],
        event["category_label"],
        event["entity"]["label"] if event["entity"] else "",
        event["reason"] or "",
    ]
    for change in event["changes"]:
        visible += [change["label"], change["before"] or "", change["after"]]

    for text in visible:
        assert not UUID_PATTERN.search(text), f"identifier leaked onto the card: {text!r}"
        assert "{" not in text and "}" not in text, f"raw JSON leaked: {text!r}"

    # The checklist reads as progress, not as "2 fields, 2 fields".
    readable = {c["label"]: c["after"] for c in event["changes"]}
    assert readable["Checklist"] == "1 of 2 steps complete"


# --- F. the technical record survives ---------------------------------


async def test_the_raw_event_is_still_there_for_an_auditor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hiding the identifiers from the timeline must not lose them. An
    auditor tracing one record needs exactly the fields a normal reader
    should never be shown by default."""
    user_id, org_id = await _signup(client, "audit-tech@example.com", "Audit Tech Org")
    control = await _control(db_session, org_id, "Back up production data")

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=user_id,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(control.id),
        before_state={"status": "needs_review"},
        after_state={"status": "pass"},
    )
    await db_session.commit()

    body = (await client.get("/api/v1/audit-events", params={"limit": 20})).json()
    event = next(
        item for item in body if item["action"] == "compliance.control.assessed"
    )

    assert event["action"] == "compliance.control.assessed"
    assert event["object_id"] == str(control.id)
    assert event["object_type"] == "control"
    assert event["actor_user_id"] == str(user_id)
    assert event["before_state"] == {"status": "needs_review"}
    assert event["after_state"] == {"status": "pass"}
    assert UUID_PATTERN.fullmatch(event["id"])
    assert event["correlation_id"] is not None


# --- G. links resolve -------------------------------------------------


async def test_no_entity_link_points_into_a_withdrawn_module(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "audit-links@example.com", "Audit Links Org")
    control = await _control(db_session, org_id, "Log administrative access")
    policy = Policy(organization_id=org_id, title="AI Governance Policy", status="needs_review")
    db_session.add(policy)
    await db_session.flush()

    for object_type, object_id in (("control", control.id), ("policy", policy.id)):
        await record_event(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            action="compliance.policy.approved"
            if object_type == "policy"
            else "compliance.control.assessed",
            object_type=object_type,
            object_id=str(object_id),
            after_state={"status": "approved"},
        )
    await db_session.commit()

    body = (await client.get("/api/v1/audit-events", params={"limit": 20})).json()
    linked = [item for item in body if item["entity"] and item["entity"]["href"]]
    assert linked, "nothing resolved to a link at all"

    for item in linked:
        href = item["entity"]["href"]
        for prefix in RETIRED_ROUTE_PREFIXES:
            assert not href.startswith(prefix), f"{href} points at withdrawn {prefix}"


async def test_a_deleted_record_says_so_instead_of_showing_a_uuid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "audit-deleted@example.com", "Audit Deleted Org")
    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(uuid.uuid4()),  # never existed, or since removed
        after_state={"status": "pass"},
    )
    await db_session.commit()

    body = (await client.get("/api/v1/audit-events", params={"limit": 20})).json()
    event = body[0]
    assert event["entity"]["available"] is False
    assert event["entity"]["label"] == "Deleted control"
    assert not UUID_PATTERN.search(event["entity"]["label"])


# --- H. search --------------------------------------------------------


async def test_search_finds_events_by_the_name_of_what_changed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "audit-search@example.com", "Audit Search Org")
    wanted = await _control(db_session, org_id, "Monitor AI systems in production")
    other = await _control(db_session, org_id, "Encrypt backups")

    for control in (wanted, other):
        await record_event(
            db_session,
            organization_id=org_id,
            actor_user_id=user_id,
            action="compliance.control.assessed",
            object_type="control",
            object_id=str(control.id),
            after_state={"status": "pass"},
        )
    await db_session.commit()

    by_name = (
        await client.get("/api/v1/audit-events", params={"q": "Monitor AI systems"})
    ).json()
    assert [item["entity"]["label"] for item in by_name] == [
        "Monitor AI systems in production"
    ]

    # The same box still traces a raw id — an auditor with a UUID in hand
    # should not need a second field.
    by_id = (await client.get("/api/v1/audit-events", params={"q": str(other.id)})).json()
    assert [item["entity"]["label"] for item in by_id] == ["Encrypt backups"]


async def test_search_cannot_reach_another_organizations_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_id, owner_org = await _signup(client, "audit-owner@example.com", "Audit Owner Org")
    theirs = await _control(db_session, owner_org, "Their private control")
    await record_event(
        db_session,
        organization_id=owner_org,
        actor_user_id=owner_id,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(theirs.id),
        after_state={"status": "pass"},
    )
    await db_session.commit()

    await _signup(client, "audit-intruder@example.com", "Audit Intruder Org")
    body = (
        await client.get("/api/v1/audit-events", params={"q": "Their private control"})
    ).json()
    assert body == []


async def test_filtering_by_actor_kind_is_applied_by_the_database(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "audit-filter@example.com", "Audit Filter Org")
    control = await _control(db_session, org_id, "Review access quarterly")

    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=user_id,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(control.id),
        after_state={"status": "pass"},
    )
    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=user_id,
        action="compliance.gap.remediation_generated",
        object_type="control",
        object_id=str(control.id),
        after_state={"checklist_items": 4},
    )
    await db_session.commit()

    people = (await client.get("/api/v1/audit-events", params={"actor_kind": "person"})).json()
    # `auth.signup` is a person's action too — it is the account being
    # created — so the assertion is that the AI event is absent, not that
    # the trail holds one row.
    assert "compliance.control.assessed" in {item["action"] for item in people}
    assert "compliance.gap.remediation_generated" not in {item["action"] for item in people}

    ai = (await client.get("/api/v1/audit-events", params={"actor_kind": "ai"})).json()
    assert {item["action"] for item in ai} == {"compliance.gap.remediation_generated"}


# --- the translation itself -------------------------------------------


def test_every_change_is_a_phrase_rather_than_a_json_fragment() -> None:
    changes = summarize_change(
        "compliance.control.assessed", {"status": "needs_review"}, {"status": "pass"}
    )
    assert [(c.label, c.before, c.after) for c in changes] == [
        ("Status", "Needs review", "Passed")
    ]

    # A key this module has not been taught about is humanized rather
    # than dropped: it is still the customer's data.
    unknown = summarize_change("x.y.z", None, {"some_new_field": "value_here"})
    assert unknown[0].label == "Some new field"
    assert unknown[0].after == "value here"


def test_a_reason_is_lifted_out_of_the_state_rather_than_listed_as_a_field() -> None:
    assert reason_from({"status": "pass", "notes": "Confirmed sufficient."}) == (
        "Confirmed sufficient."
    )
    changes = summarize_change("a.b.c", None, {"status": "pass", "notes": "Confirmed."})
    assert [c.label for c in changes] == ["Status"]


def test_values_read_the_way_the_rest_of_the_product_reads_them() -> None:
    assert format_value("needs_review") == "Needs review"
    assert format_value(True) == "Yes"
    assert format_value(None) == "—"
    assert format_value(1234) == "1,234"


def test_every_action_the_product_records_has_a_title() -> None:
    """A feed may be incomplete. It may never leak an internal name."""
    for action in (
        "compliance.control.assessed",
        "compliance.framework.assessed",
        "compliance.gap.remediation_updated",
        "core.file.upload_requested",
        "compliance.evidence.suggestion_approved",
        "compliance.policy.approved",
    ):
        assert action in TITLES
        assert "." not in TITLES[action]
        assert "_" not in TITLES[action]


def test_events_sort_into_the_filter_a_reader_would_look_under() -> None:
    assert category_for("compliance.gap.resolved") == "gaps"
    assert category_for("core.file.upload_requested") == "evidence"
    assert category_for("compliance.policy.approved") == "policies"
    assert category_for("compliance.dsar.received") == "privacy"
    assert category_for("auth.login") == "security"


async def test_the_view_layer_never_falls_back_to_a_machine_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An action with no entry gets a humanized last segment, never the
    dotted path."""
    _, org_id = await _signup(client, "audit-unknown@example.com", "Audit Unknown Org")
    await record_event(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        action="somemodule.thing.some_new_action",
        object_type="thing",
        object_id=None,
        after_state=None,
    )
    await db_session.commit()

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org_id,
                    AuditEvent.action == "somemodule.thing.some_new_action",
                )
            )
        )
        .scalars()
        .all()
    )
    views = await build_views(db_session, organization_id=org_id, events=events)
    assert views[0].title == "Some new action"
    assert "." not in views[0].title
