"""Veyntra is an AI compliance product, and DSAR must say only what it knows.

The failure these guard against had a specific shape. Discovery searched
`support_customers`, `support_tickets`, `sales_contacts` and
`sales_leads` — tables belonging to product modules Veyntra no longer
ships — and reported "0 matches" for each. A case worker reading that
zero would sign a response saying no data was found, on the strength of
a query against systems this product does not operate. That is worse
than not looking, because it looks like having looked.

Two rules follow, and every test here is one of them.

**Only a real store, really reachable, is searchable.** Not "the table
happens to be in our database". A processing activity is compliance
context; a vendor is somebody else's system; an integration is
searchable when the organization connected it *and* an adapter exists.

**Relevance is about the person, never about our plumbing.** The
ranking used to read "Veyntra can search this directly, so including it
costs nothing" — which made the cheapest source to search automatically
the most relevant one. Those are different questions and they now live
in different fields.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import dsar_sources


async def _org(client: AsyncClient, email: str) -> None:
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


async def _scope(client: AsyncClient, dsar_id: str) -> dict[str, dict]:
    rows = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    return {row["name"]: row for row in rows}


# --- §21: no legacy product module can appear ---------------------------

# Every name the removed discovery used to produce. Named literally
# rather than by pattern: this list is the regression, and a future
# reader should be able to see exactly what used to leak.
LEGACY_NAMES = (
    "Support records",
    "Support — customers",
    "Support — tickets",
    "Sales — contacts",
    "Sales — leads",
)


@pytest.mark.asyncio
async def test_no_legacy_sales_or_support_source_appears_in_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "reg1@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)

    names = set(await _scope(client, dsar["id"]))

    for legacy in LEGACY_NAMES:
        assert legacy not in names, f"{legacy} is still offered as a DSAR source"


@pytest.mark.asyncio
async def test_the_native_registry_holds_nothing_from_a_removed_module() -> None:
    """The registry is the single place a searchable source can be
    declared, so this is where the absence has to hold."""
    keys = {source.key for source in dsar_sources.NATIVE_SOURCES}
    assert keys == {"internal:identity"}
    assert "internal:support" not in keys
    assert "internal:sales" not in keys


@pytest.mark.asyncio
async def test_dsar_discovery_imports_no_legacy_module() -> None:
    """A source cannot come back by accident if the import is gone.

    Read as text rather than by importing: the point is that the coupling
    is absent from the file, not merely unused at runtime.
    """
    from pathlib import Path

    package = Path(dsar_sources.__file__).parent
    for name in ("dsar.py", "dsar_scope.py", "dsar_discovery.py", "dsar_sources.py"):
        text = (package / name).read_text(encoding="utf-8")
        assert "app.sales" not in text, f"{name} still reaches into the Sales module"
        assert "app.support" not in text, f"{name} still reaches into the Support module"


# --- §3/§5: user accounts stay, honestly ranked -------------------------


@pytest.mark.asyncio
async def test_user_accounts_remain_searchable_but_only_possibly_relevant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5's example. Veyntra genuinely holds account records, so it can
    search them — and most people making an access request have no
    account, so "possible" is the honest ranking."""
    await _org(client, "reg2@northwind-example.com")
    dsar = await _jane(client)

    accounts = (await _scope(client, dsar["id"]))["User accounts"]

    assert accounts["search_capability"] == "searchable"
    assert accounts["relevance"] == "possible"
    assert "can be checked against" in accounts["relevance_reason"]
    # §12: the ranking must not argue from what it costs us.
    assert "costs nothing" not in accounts["relevance_reason"]
    assert "cheap" not in accounts["relevance_reason"].lower()


@pytest.mark.asyncio
async def test_no_relevance_reason_argues_from_search_cost(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12, applied across every source the product proposes."""
    await _org(client, "reg3@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    await _activity(client, "Employee medical-leave administration", "Employees", "Leave.")
    dsar = await _jane(client)

    for name, row in (await _scope(client, dsar["id"])).items():
        reason = (row["relevance_reason"] or "").lower()
        for phrase in ("costs nothing", "cheap", "easy to search", "can search this directly"):
            assert phrase not in reason, f"{name} ranks itself by search cost: {reason}"


# --- §22/§23: relevance and searchability move independently ------------


@pytest.mark.asyncio
async def test_relevance_and_searchability_are_independent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§22's acceptance test, stated as the property it protects.

    The searchable source is only possibly relevant; the highly relevant
    one cannot be searched at all. If ranking were still a function of
    capability, this pairing could not exist.
    """
    await _org(client, "reg4@northwind-example.com")
    await _activity(
        client,
        "AI Customer Support",
        "Customers and customer employees who contact support",
        "Answering product questions.",
    )
    dsar = await _jane(client)
    scope = await _scope(client, dsar["id"])

    assert scope["User accounts"]["search_capability"] == "searchable"
    assert scope["User accounts"]["relevance"] == "possible"

    assert scope["AI Customer Support"]["relevance"] == "high"
    assert scope["AI Customer Support"]["search_capability"] == "manual_follow_up"


@pytest.mark.asyncio
async def test_the_jane_doe_scope_matches_the_expected_result(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§18, end to end: exactly three sources, ranked and preselected as
    specified, with nothing from a removed module."""
    await _org(client, "reg5@northwind-example.com")
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
        "Administering statutory leave.",
    )
    dsar = await _jane(client)
    scope = await _scope(client, dsar["id"])

    assert set(scope) == {
        "User accounts",
        "AI Customer Support",
        "Employee medical-leave administration",
    }

    accounts = scope["User accounts"]
    assert (accounts["relevance"], accounts["search_capability"]) == (
        "possible",
        "searchable",
    )
    assert accounts["included"] is True

    support = scope["AI Customer Support"]
    assert (support["relevance"], support["search_capability"]) == (
        "high",
        "manual_follow_up",
    )
    # §23: high relevance is preselected even though nothing can search it.
    assert support["included"] is True

    medical = scope["Employee medical-leave administration"]
    assert medical["relevance"] == "low"
    # §23: probably-unrelated is not preselected, and not excluded either.
    assert medical["included"] is None
    assert "no employment relationship is known" in medical["relevance_reason"]


# --- §8/§9: a RoPA entry resolves to real systems ------------------------


@pytest.mark.asyncio
async def test_a_processing_activity_resolves_to_the_systems_behind_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: the activity says where to look next. It is not itself the
    database holding the person's records."""
    await _org(client, "reg6@northwind-example.com")
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "US"},
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "AI Support Assistant",
            "vendor": "OpenAI",
            "purpose": "Answering customer product questions in the support inbox.",
            "affected_users": ["Customers"],
            "processed_data": [{"name": "Contact details", "classification": "confidential"}],
        },
    )
    drafts = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    activity = next(row for row in drafts if row["kind"] == "processing_activity")
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{activity['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )

    dsar = await _jane(client)
    scope = await _scope(client, dsar["id"])
    row = next(
        value for key, value in scope.items() if value["kind"] == "processing_activity"
    )

    by_name = {system["name"]: system for system in row["potential_sources"]}
    assert "AI Support Assistant" in by_name
    assert "OpenAI" in by_name
    # A system nobody connected cannot be searched, and says which.
    assert by_name["AI Support Assistant"]["capability"] == "not_connected"
    # A processor's systems are never ours to search, connected or not.
    assert by_name["OpenAI"]["capability"] == "processor_follow_up"
    # The activity itself inherits the honest answer.
    assert row["search_capability"] == "manual_follow_up"


# --- §24: an unconnected source is never reported as empty --------------


@pytest.mark.asyncio
async def test_a_relevant_activity_with_no_integration_reports_follow_up_not_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§24, and the reason this whole change exists."""
    await _org(client, "reg7@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]

    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={"verified": True, "method": "Email verification", "notes": "Link confirmed."},
    )
    scope = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm",
        json={
            "decisions": [
                {"source_key": row["source_key"], "included": True} for row in scope
            ]
        },
    )

    items = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    ).json()
    by_name = {item["source_name"]: item for item in items}

    activity = by_name["AI Customer Support"]
    assert activity["search_state"] == "manual_follow_up"
    assert activity["matches"] == 0
    assert "has not searched" in activity["state_detail"]
    # A real task, not just a label -- §15.
    assert activity["task_id"] is not None

    # And the one source Veyntra genuinely owns really was searched.
    accounts = by_name["User accounts"]
    assert accounts["search_state"] == "searched_none"
    assert accounts["state_detail"] is None


@pytest.mark.asyncio
async def test_a_connected_integration_without_an_adapter_is_not_called_searchable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19/§20: connecting a tool is necessary but not sufficient.

    Until somebody writes a DSAR search adapter for a connector, the
    honest answer is that a person has to search it in the tool itself.
    Claiming otherwise would be a fake integration.
    """
    connected = {"zendesk": "Zendesk"}

    capability, detail = dsar_sources.capability_for_system(
        name="Zendesk", connector_key="zendesk", connected=connected
    )
    assert capability == dsar_sources.MANUAL_FOLLOW_UP
    assert "no data-request search for it yet" in detail

    # Nothing connected at all is a different, and also honest, answer.
    capability, detail = dsar_sources.capability_for_system(
        name="Zendesk", connector_key="zendesk", connected={}
    )
    assert capability == dsar_sources.NOT_CONNECTED
    assert "No Veyntra integration is configured" in detail


@pytest.mark.asyncio
async def test_a_connector_with_an_adapter_becomes_searchable() -> None:
    """The extensibility the registry exists for: one entry, no changes
    anywhere else in DSAR."""
    dsar_sources.DSAR_SEARCH_ADAPTERS["zendesk"] = lambda **_: None  # type: ignore[assignment]
    try:
        capability, detail = dsar_sources.capability_for_system(
            name="Zendesk", connector_key="zendesk", connected={"zendesk": "Zendesk"}
        )
        assert capability == dsar_sources.SEARCHABLE
        assert "can be searched directly" in detail
    finally:
        dsar_sources.DSAR_SEARCH_ADAPTERS.pop("zendesk", None)


# --- §13: an unknown requester rules nothing out ------------------------


@pytest.mark.asyncio
async def test_an_unknown_relationship_ranks_everything_possible(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§13: do not over-assume. With no domain to reason from, an
    employee activity cannot be ranked down."""
    await _org(client, "reg8@northwind-example.com")
    await _activity(client, "Employee medical-leave administration", "Employees", "Leave.")
    anonymous = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Unknown Requester",
                "requester_email": "postal-request",
                "request_type": "access",
            },
        )
    ).json()

    row = (await _scope(client, anonymous["id"]))["Employee medical-leave administration"]
    assert row["relevance"] == "possible"
    assert "not known" in row["relevance_reason"]


# --- §16/§17: the package counts what actually happened -----------------


@pytest.mark.asyncio
async def test_the_package_reports_outstanding_sources_rather_than_implying_completeness(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: "searched and empty" and "not searched" are counted apart.

    A package that added them together would claim a completeness it does
    not have — which is the same error as reporting an unreachable source
    as zero, one layer up.
    """
    await _org(client, "reg9@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]

    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={"verified": True, "method": "Email verification", "notes": "Link confirmed."},
    )
    scope = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm",
        json={
            "decisions": [
                {"source_key": row["source_key"], "included": True} for row in scope
            ]
        },
    )
    items = (
        await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discovery/run")
    ).json()
    for item in items:
        if item["review_decision"] == "needs_review":
            await client.patch(
                f"/api/v1/compliance/dsars/{dsar_id}/discovered/{item['id']}",
                json={
                    "review_decision": "include",
                    "review_reason": "Awaiting the manual search.",
                },
            )

    preview = (
        await client.get(f"/api/v1/compliance/dsars/{dsar_id}/response/preview")
    ).json()
    coverage = preview["coverage"]

    assert coverage["scope_confirmed"] == 2
    # One store Veyntra owns and really queried.
    assert coverage["automatically_searched"] == 1
    assert coverage["searched_no_matches"] == 1
    # One activity nobody can search yet.
    assert coverage["outstanding"] == 1
    assert coverage["complete"] is False

    # A partial response can still be approved -- an interim reply is
    # legitimate, and the package says outright that it is partial.
    approved = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/response/approve",
        json={"digest": preview["digest"]},
    )
    assert approved.status_code == 200, approved.text

    # §16: what is refused is calling the request finished while a source
    # in scope has not been searched.
    refused = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/response/sent")
    assert refused.status_code == 422
    message = refused.json()["error"]["message"]
    assert "have not been searched" in message
    assert "AI Customer Support" in message


@pytest.mark.asyncio
async def test_excluding_a_likely_relevant_source_requires_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§14: a narrowed scope carries its own justification.

    Agreeing that a "probably unrelated" source is unrelated needs no
    explanation — the reasoning is already on screen. Overriding a
    high-relevance ranking does.
    """
    await _org(client, "reg10@northwind-example.com")
    await _activity(client, "AI Customer Support", "Customers", "Support.")
    await _activity(client, "Employee medical-leave administration", "Employees", "Leave.")
    dsar = await _jane(client)
    dsar_id = dsar["id"]
    scope = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()

    refused = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm",
        json={
            "decisions": [
                {"source_key": row["source_key"], "included": False} for row in scope
            ]
        },
    )
    assert refused.status_code == 422
    message = refused.json()["error"]["message"]
    assert "AI Customer Support" in message
    # The low-relevance one is not named: agreeing with the product's own
    # argument is not a decision that needs defending.
    assert "Employee medical-leave administration" not in message

    allowed = await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/scope/confirm",
        json={
            "decisions": [
                {
                    "source_key": row["source_key"],
                    "included": False,
                    "exclusion_reason": "Handled under a separate request.",
                }
                for row in scope
            ]
        },
    )
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_somebody_elses_staff_are_not_read_as_our_workforce(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6's expected reasoning, and the distinction it turns on.

    "Customer employees who contact support" are the customer's staff.
    Reading them as workforce data made the ranking argue that the
    activity covered this organization's own employees — the right answer
    for the wrong reason, which is worse than useless when the whole
    point of showing the reasoning is that a reviewer can check it.
    """
    await _org(client, "reg11@northwind-example.com")
    await _activity(
        client,
        "AI Customer Support",
        "Customers and customer employees who contact support",
        "Answering product questions in the support inbox.",
    )
    dsar = await _jane(client)

    row = (await _scope(client, dsar["id"]))["AI Customer Support"]

    assert row["relevance"] == "high"
    assert "explicitly covers customer records" in row["relevance_reason"]
    assert "customer access request" in row["relevance_reason"]
    # And it does not claim to cover this organization's own workforce.
    assert "both employees and customers" not in row["relevance_reason"]
