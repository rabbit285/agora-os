"""The Jane Doe walkthrough, and the rules that hold it up.

§19 describes nine steps. The first test walks all of them end to end,
because the value of this feature is the sequence — each step handing the
next one something it could not have assembled itself.

The rest are the guarantees the sequence rests on, and each is a failure
that would be invisible from the happy path:

- a low-relevance source is ranked down but never dropped, because a
  filter that is wrong costs a response its completeness;
- discovery obeys the confirmed scope exactly, because otherwise
  confirming it is theatre;
- a source Veyntra cannot reach reports "not searched", never "0
  records", because those mean opposite things to somebody signing a
  response;
- re-running anything is safe, because "Refresh" must not triple a list
  or un-redact a decision;
- and what is approved is what is sent.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import DsarDiscoveredItem, DsarScopeSource


async def _org(client: AsyncClient, email: str = "privacy@northwind-example.com") -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Priya Raman",
            "organization_name": "Northwind",
        },
    )


async def _activity(client: AsyncClient, name: str, subjects: str, purpose: str) -> dict:
    return (
        await client.post(
            "/api/v1/compliance/processing-activities",
            json={
                "name": name,
                "purpose": purpose,
                "legal_basis": "contract",
                "data_subjects": subjects,
                "retention_period": "24 months",
            },
        )
    ).json()


async def _jane(client: AsyncClient) -> dict:
    return (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Jane Doe",
                "requester_email": "janedoe@gmail.com",
                "request_type": "access",
            },
        )
    ).json()


async def _verify(client: AsyncClient, dsar_id: str) -> dict:
    return (
        await client.post(
            f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
            json={
                "verified": True,
                "method": "Email verification to address on file",
                "notes": "Requester confirmed ownership through verification link.",
            },
        )
    ).json()


async def _confirm_all(client: AsyncClient, dsar_id: str, *, exclude: set[str] = frozenset()):
    scope = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    return await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm",
        json={
            "decisions": [
                {
                    "source_key": row["source_key"],
                    "included": row["name"] not in exclude,
                    # Leaving out something the product ranked likely
                    # relevant is a judgement, and it has to be recorded
                    # as one.
                    "exclusion_reason": (
                        "Reviewed and judged out of scope for this request."
                        if row["name"] in exclude
                        else None
                    ),
                }
                for row in scope
            ]
        },
    )


# --- §19: the whole walk ------------------------------------------------


@pytest.mark.asyncio
async def test_the_jane_doe_request_walks_from_intake_to_completion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client)
    await _activity(
        client,
        "AI Customer Support",
        "Customers and customer employees who contact support",
        "Answering product questions in the support inbox.",
    )
    await _activity(
        client,
        "Employee medical-leave administration",
        "Employees",
        "Administering statutory and contractual leave.",
    )
    dsar = await _jane(client)
    dsar_id = dsar["id"]

    # Step 1 — identity first. Nothing else is offered.
    workflow = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/workflow")).json()
    assert workflow["phase"] == "identity_verification"
    assert workflow["next_action"]["label"] == "Verify requester identity"

    # Searching before verifying is refused, not merely discouraged.
    early = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    assert early.status_code == 422
    assert "identity" in early.json()["error"]["message"].lower()

    verified = await _verify(client, dsar_id)
    assert verified["verification_status"] == "verified"
    assert verified["verification_notes"].startswith("Requester confirmed")

    # Step 2 — ranked candidates, with the reasoning shown.
    scope = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    by_name = {row["name"]: row for row in scope}

    support = by_name["AI Customer Support"]
    assert support["relevance"] == "high"
    assert support["included"] is True
    # The argument is about this person, not about what is easy to
    # search -- and it names the customer relationship it turns on.
    assert "customer records" in support["relevance_reason"].lower()
    assert "costs nothing" not in support["relevance_reason"]

    medical = by_name["Employee medical-leave administration"]
    assert medical["relevance"] == "low"
    # Ranked down, and left for a person to decide -- not excluded.
    assert medical["included"] is None
    assert "gmail.com" in medical["relevance_reason"]

    # Step 3 — a scope with anything undecided is not a confirmed scope.
    premature = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm", json={"decisions": []}
    )
    assert premature.status_code == 422
    assert "no decision yet" in premature.json()["error"]["message"]

    confirmed = await _confirm_all(
        client, dsar_id, exclude={"Employee medical-leave administration"}
    )
    assert confirmed.status_code == 200

    workflow = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/workflow")).json()
    assert workflow["phase"] == "discovery"

    # Step 4 — the plan, then the run.
    plan = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/discovery-plan")).json()
    assert plan["connected"] >= 1
    assert plan["manual"] >= 1
    assert plan["excluded"] == 1

    items = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    ).json()
    states = {item["source_name"]: item["search_state"] for item in items}

    # Step 5 — the states are distinguishable.
    assert states["User accounts"] in ("searched_none", "searched_found")
    assert states["AI Customer Support"] == "manual_follow_up"
    # The excluded source was not searched, and says so.
    assert states["Employee medical-leave administration"] == "not_searched"

    # Step 6 — the manual source waits for a person; nothing else does.
    workflow = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/workflow")).json()
    assert workflow["phase"] == "response_review"
    assert workflow["needs_review"] >= 1

    for item in items:
        if item["review_decision"] == "needs_review":
            response = await client.patch(
                f"/api/v1/compliance/dsars/{dsar_id}/discovered/{item['id']}",
                json={
                    "review_decision": "include",
                    "review_reason": "Confirmed with the system owner.",
                },
            )
            assert response.status_code == 200

    # Step 7 — Veyntra drafts.
    preview = (
        await client.get(f"/api/v1/compliance/dsars/{dsar_id}/response/preview")
    ).json()
    assert "Jane Doe" in preview["letter"]
    assert preview["identity_method"] == "Email verification to address on file"
    # The gap is named in the letter itself, not buried.
    assert preview["not_searched"]
    assert "followed up separately" in preview["letter"]

    # Step 8 — approve exactly what was read.
    approved = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/response/approve",
        json={"digest": preview["digest"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Step 9 — completion is blocked while a source in scope has not
    # actually been searched. §16: the manual follow-up is the work, and
    # the request is not finished until somebody does it.
    blocked = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/response/sent")
    assert blocked.status_code == 422
    message = blocked.json()["error"]["message"]
    assert "have not been searched" in message
    assert "AI Customer Support" in message

    tasks = (await client.get("/api/v1/tasks")).json()
    follow_up = next(task for task in tasks if task["entity_type"] == "dsar")
    await client.patch(f"/api/v1/tasks/{follow_up['id']}", json={"status": "done"})

    sent = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/response/sent")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"

    final = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()
    assert final["status"] == "fulfilled"
    assert final["phase"] == "completed"


# --- §3: rank, never filter ---------------------------------------------


@pytest.mark.asyncio
async def test_an_activity_with_no_recorded_subjects_is_not_ranked_down(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The record most likely to be a blind spot must not be demoted for
    being incomplete."""
    await _org(client, "privacy2@northwind-example.com")
    await _activity(client, "Legacy archive", "Not recorded", "Historic records.")
    dsar = await _jane(client)

    scope = (await client.get(f"/api/v1/compliance/dsars/{dsar['id']}/scope")).json()
    row = next(item for item in scope if item["name"] == "Legacy archive")
    assert row["relevance"] == "possible"
    assert "cannot be judged" in row["relevance_reason"]


@pytest.mark.asyncio
async def test_an_employee_writing_from_the_company_domain_ranks_employee_records_high(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The same activity, the opposite requester, the opposite ranking."""
    await _org(client, "privacy3@northwind-example.com")
    await _activity(
        client, "Employee medical-leave administration", "Employees", "Leave."
    )
    internal = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Sam Okafor",
                "requester_email": "sam@northwind-example.com",
                "request_type": "access",
            },
        )
    ).json()

    scope = (await client.get(f"/api/v1/compliance/dsars/{internal['id']}/scope")).json()
    row = next(
        item for item in scope if item["name"] == "Employee medical-leave administration"
    )
    assert row["relevance"] == "high"
    assert row["included"] is True


# --- §5/§7: discovery tells the truth about what it did -----------------


@pytest.mark.asyncio
async def test_discovery_obeys_the_confirmed_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Otherwise confirming the scope is theatre."""
    await _org(client, "privacy4@northwind-example.com")
    await _activity(client, "Marketing list", "Customers", "Newsletters.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id, exclude={"Marketing list"})

    items = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    ).json()
    excluded = next(item for item in items if item["source_name"] == "Marketing list")
    assert excluded["search_state"] == "not_searched"
    assert "Excluded from the confirmed search scope" in excluded["state_detail"]


@pytest.mark.asyncio
async def test_an_unreachable_source_reports_not_searched_rather_than_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§7, and the reason the five states exist.

    The old code reported an unsearchable processor as "0 matches",
    which reads as evidence of absence. It is the absence of evidence.
    """
    await _org(client, "privacy5@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)

    items = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    ).json()
    unreachable = next(
        item for item in items if item["source_name"] == "AI Customer Support"
    )
    assert unreachable["search_state"] == "manual_follow_up"
    assert unreachable["matches"] == 0
    assert "has not searched" in unreachable["state_detail"]

    # §20: it becomes somebody's task rather than a silent gap.
    assert unreachable["task_id"] is not None
    tasks = (await client.get("/api/v1/tasks")).json()
    task = next(row for row in tasks if row["id"] == unreachable["task_id"])
    assert "AI Customer Support" in task["title"]
    assert task["entity_id"] == dsar_id


@pytest.mark.asyncio
async def test_a_searched_and_empty_source_is_distinguishable_from_an_unsearched_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy6@northwind-example.com")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)

    items = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    ).json()
    searched = next(item for item in items if item["source_name"] == "User accounts")
    # Jane has no account, and Veyntra genuinely looked.
    assert searched["search_state"] == "searched_none"
    assert searched["state_detail"] is None
    assert searched["review_decision"] == "include"


# --- §18: repeating anything is safe ------------------------------------


@pytest.mark.asyncio
async def test_re_running_discovery_does_not_duplicate_rows_or_tasks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy7@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)

    first = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()
    second = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()
    third = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()

    assert len(first) == len(second) == len(third)
    rows = (
        await db_session.execute(
            select(DsarDiscoveredItem).where(
                DsarDiscoveredItem.dsar_id == uuid.UUID(dsar_id)
            )
        )
    ).scalars().all()
    assert len(rows) == len(first)

    tasks = (await client.get("/api/v1/tasks")).json()
    dsar_tasks = [task for task in tasks if task["entity_id"] == dsar_id]
    assert len(dsar_tasks) == 1


@pytest.mark.asyncio
async def test_re_running_discovery_preserves_a_review_decision(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The failure this guards: somebody redacts an internal note, hits
    refresh, and silently un-redacts it."""
    await _org(client, "privacy8@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)

    items = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()
    target = next(item for item in items if item["search_state"] == "manual_follow_up")
    await client.patch(
        f"/api/v1/compliance/dsars/{dsar_id}/discovered/{target['id']}",
        json={
            "review_decision": "redact",
            "review_reason": "Contains another customer's details in the thread.",
        },
    )

    again = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()
    after = next(item for item in again if item["id"] == target["id"])
    assert after["review_decision"] == "redact"
    assert "another customer" in after["review_reason"]


@pytest.mark.asyncio
async def test_re_reading_the_scope_does_not_duplicate_or_reset_decisions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy9@northwind-example.com")
    await _activity(client, "Marketing list", "Customers", "Newsletters.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]

    first = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    target = next(row for row in first if row["name"] == "Marketing list")
    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm",
        json={
            "decisions": [
                {"source_key": row["source_key"], "included": row["name"] != "Marketing list"}
                for row in first
            ]
        },
    )

    for _ in range(3):
        again = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()

    assert len(again) == len(first)
    rows = (
        await db_session.execute(
            select(DsarScopeSource).where(DsarScopeSource.dsar_id == uuid.UUID(dsar_id))
        )
    ).scalars().all()
    assert len(rows) == len(first)
    # The exclusion survived three refreshes.
    assert next(r for r in again if r["source_key"] == target["source_key"])["included"] is False


@pytest.mark.asyncio
async def test_adding_the_same_manual_source_twice_adds_it_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy10@northwind-example.com")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    body = {"name": "Legacy CRM export", "reason": "Held offline by the ops team."}

    first = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/scope/sources", json=body)
    ).json()
    second = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/scope/sources", json=body)
    ).json()

    assert first["id"] == second["id"]
    assert first["added_by_user"] is True
    # A source a person added is theirs to search, not Veyntra's to
    # claim: nothing is connected to it.
    assert first["search_capability"] == "not_connected"


# --- §9/§10: the disclosure decision belongs to a person ----------------


@pytest.mark.asyncio
async def test_excluding_a_record_set_requires_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An unexplained exclusion is indistinguishable, later, from an
    accident."""
    await _org(client, "privacy11@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)
    items = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()
    target = next(item for item in items if item["search_state"] == "manual_follow_up")

    refused = await client.patch(
        f"/api/v1/compliance/dsars/{dsar_id}/discovered/{target['id']}",
        json={"review_decision": "exclude"},
    )
    assert refused.status_code == 422
    assert "defensible" in refused.json()["error"]["message"]


@pytest.mark.asyncio
async def test_health_related_sources_are_flagged_for_review_not_decided(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: Veyntra notices; it does not conclude. Article 15(4) is a
    legal judgement about specific content."""
    await _org(client, "privacy12@northwind-example.com")
    await _activity(
        client,
        "Employee medical-leave administration",
        "Employees and customers",
        "Administering sickness leave.",
    )
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)

    items = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()
    medical = next(
        item
        for item in items
        if item["source_name"] == "Employee medical-leave administration"
    )
    assert any("special-category" in flag for flag in medical["sensitivity_flags"])
    # Flagged, and left undecided.
    assert medical["review_decision"] == "needs_review"


# --- §12: what is approved is what is sent -------------------------------


@pytest.mark.asyncio
async def test_approving_a_stale_preview_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The approval has to be of a specific text, or it approves nothing."""
    await _org(client, "privacy13@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)
    items = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")).json()

    preview = (
        await client.get(f"/api/v1/compliance/dsars/{dsar_id}/response/preview")
    ).json()
    stale = preview["digest"]

    # The findings move after the preview was read.
    target = next(item for item in items if item["review_decision"] == "needs_review")
    await client.patch(
        f"/api/v1/compliance/dsars/{dsar_id}/discovered/{target['id']}",
        json={"review_decision": "redact", "review_reason": "Third-party content."},
    )

    refused = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/response/approve", json={"digest": stale}
    )
    assert refused.status_code == 422
    assert "changed since" in refused.json()["error"]["message"]


@pytest.mark.asyncio
async def test_the_export_renders_the_approved_snapshot_not_the_live_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12's core promise. If the export rebuilt from live records the
    answer could change between approval and delivery."""
    await _org(client, "privacy14@northwind-example.com")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)
    await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")

    preview = (
        await client.get(f"/api/v1/compliance/dsars/{dsar_id}/response/preview")
    ).json()
    approved = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/response/approve",
        json={
            "digest": preview["digest"],
            "letter": "Dear Jane,\n\nThis is the wording we agreed.\n",
        },
    )
    assert approved.status_code == 200, approved.text

    # A source is added after approval. The export must not absorb it.
    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/sources",
        json={"name": "Newly remembered archive", "reason": "Found later."},
    )

    export = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/export")
    assert export.status_code == 200
    body = export.text
    assert "This is the wording we agreed." in body
    assert "Newly remembered archive" not in body


@pytest.mark.asyncio
async def test_approving_the_same_response_twice_makes_one_package(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy15@northwind-example.com")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    await _verify(client, dsar_id)
    await _confirm_all(client, dsar_id)
    await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")

    preview = (
        await client.get(f"/api/v1/compliance/dsars/{dsar_id}/response/preview")
    ).json()
    first = (
        await client.post(
            f"/api/v1/compliance/dsars/{dsar_id}/response/approve",
            json={"digest": preview["digest"]},
        )
    ).json()
    second = (
        await client.post(
            f"/api/v1/compliance/dsars/{dsar_id}/response/approve",
            json={"digest": preview["digest"]},
        )
    ).json()

    assert first["id"] == second["id"]
    assert first["version"] == second["version"] == 1


# --- §1/§13: identity gates everything ----------------------------------


@pytest.mark.asyncio
async def test_a_failed_verification_blocks_the_request_and_says_why(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy16@northwind-example.com")
    dsar = await _jane(client)
    dsar_id = dsar["id"]

    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={
            "verified": False,
            "method": "Email verification to address on file",
            "notes": "Verification link was never opened; no reply after two attempts.",
        },
    )

    workflow = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/workflow")).json()
    assert workflow["phase"] == "blocked"
    assert workflow["blockers"][0]["code"] == "identity_failed"

    record = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()
    # The reason a verification failed is exactly what a second attempt,
    # or a complaint, needs to read.
    assert "never opened" in record["verification_notes"]

    refused = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    assert refused.status_code == 422


@pytest.mark.asyncio
async def test_a_request_from_another_organization_is_not_reachable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "privacy17@northwind-example.com")
    theirs = await _jane(client)
    await _org(client, "privacy18@othercorp-example.com")

    for path in ("workflow", "scope", "discovered", "discovery-plan"):
        response = await client.get(f"/api/v1/compliance/dsars/{theirs['id']}/{path}")
        assert response.status_code == 404, path


# --- §14: the status says what to do, not merely that work exists -------


@pytest.mark.asyncio
async def test_a_new_request_is_already_at_identity_verification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"Received" is a fact about the past. The list should say what the
    request needs, from the moment it is logged."""
    await _org(client, "privacy19@northwind-example.com")
    created = await _jane(client)
    assert created["phase"] == "identity_verification"

    listed = (await client.get("/api/v1/compliance/dsars")).json()
    assert next(row for row in listed if row["id"] == created["id"])["phase"] == (
        "identity_verification"
    )


@pytest.mark.asyncio
async def test_the_phase_advances_with_the_record_not_by_hand(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """There is no endpoint that sets a phase. Each one is earned."""
    await _org(client, "privacy20@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]

    seen = [(await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()["phase"]]
    await _verify(client, dsar_id)
    seen.append((await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()["phase"])
    await _confirm_all(client, dsar_id)
    seen.append((await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()["phase"])
    await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    seen.append((await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()["phase"])

    assert seen == [
        "identity_verification",
        "scope_review",
        "discovery",
        "response_review",
    ]
