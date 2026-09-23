"""What Veyntra can actually search, and what it must ask a person about.

This is the registry the rest of DSAR discovery reads. It exists to make
one claim impossible: that a source was searched when it was not.

Veyntra is an AI compliance product. It holds a register of processing
activities, AI systems and vendors — descriptions of where personal data
goes. It does not hold the customer records those descriptions are
about. So the honest default for almost everything in the register is
"a person has to go and look", and the exceptions are few and named.

Three rules.

**Searchable means a real adapter, really connected.** Not "the table is
in our database". The old discovery searched `support_customers` and
`sales_contacts` — tables belonging to product modules this product no
longer has — and reported "0 matches" for them, which reads as evidence
that a person's data is absent. It was evidence of nothing.

**A processing activity is not a data store.** "AI Customer Support" is
compliance context: it says the person's data may be in the systems used
for that processing. Resolving those systems is a second step, and each
one has its own connection state.

**Connectivity is read from what the organization configured.** An
`IntegrationConnection` row, in a working state, for a connector that has
a DSAR search adapter. Any of those missing and the source is honestly
reported as unsearched. New adapters register here; nothing about this
module hardcodes a product module.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# --- search capability -------------------------------------------------
#
# Five states, because they mean five different things to somebody
# signing a response. Only SEARCHABLE can ever produce "we looked and
# found nothing".
SEARCHABLE = "searchable"
MANUAL_FOLLOW_UP = "manual_follow_up"
PROCESSOR_FOLLOW_UP = "processor_follow_up"
NOT_CONNECTED = "not_connected"
UNSUPPORTED = "unsupported"

CAPABILITY_LABELS = {
    SEARCHABLE: "Searchable",
    MANUAL_FOLLOW_UP: "Manual follow-up",
    PROCESSOR_FOLLOW_UP: "Processor follow-up",
    NOT_CONNECTED: "Not connected",
    UNSUPPORTED: "Unsupported",
}

# --- relevance ---------------------------------------------------------
#
# What the requester and the register suggest, and nothing else. There is
# deliberately no term here for "cheap to search".
HIGH = "high"
POSSIBLE = "possible"
LOW = "low"

RELEVANCE_LABELS = {
    HIGH: "High relevance",
    POSSIBLE: "Possible relevance",
    LOW: "Probably unrelated",
}

# Ordering for the screen. Relevance decides the order; capability breaks
# ties, because among equally relevant sources the ones a person has to
# chase are the ones worth seeing early.
RELEVANCE_ORDER = {HIGH: 0, POSSIBLE: 1, LOW: 2}


Searcher = Callable[..., Awaitable[tuple[int, list[str]]]]


@dataclass(frozen=True)
class NativeSource:
    """A store Veyntra genuinely owns and can query for a person.

    The bar is deliberately high. A table is a native source only if this
    product is the system of record for it — not merely because the row
    happens to live in our database.
    """

    key: str
    name: str
    # What searching it actually checks, in the reviewer's terms.
    reason: str
    # Why it might hold this requester's data. Never mentions cost or
    # convenience: see the module docstring.
    relevance: str
    relevance_reason: str
    search: Searcher


async def _search_user_accounts(
    db: AsyncSession, *, organization_id: uuid.UUID, email: str
) -> tuple[int, list[str]]:
    """Veyntra's own account records for this email.

    Genuinely ours: an account exists because somebody signed up to this
    product. Scoped to the organization handling the request — an account
    under a different tenant is not this controller's to disclose.
    """
    from app.core.models import Membership
    from app.identity.models import User

    rows = list(
        (
            await db.execute(
                select(User.id)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == organization_id,
                    func.lower(User.email) == email,
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows), [str(row) for row in rows]


# Every Veyntra-native searchable source. One entry, because one is what
# this product genuinely holds about an outside individual.
#
# Notably absent: support customers, support tickets, sales contacts and
# sales leads. Those belong to product modules Veyntra no longer ships,
# and searching them told a case worker that a person's data was absent
# from systems this product does not operate.
NATIVE_SOURCES: tuple[NativeSource, ...] = (
    NativeSource(
        key="internal:identity",
        name="User accounts",
        reason="Veyntra organization and user account records.",
        # Possible, not high: an access request from a member of the
        # public usually has no account behind it. Worth checking,
        # not expected to match.
        relevance=POSSIBLE,
        relevance_reason=(
            "The requester's email address can be checked against this "
            "organization's Veyntra user accounts."
        ),
        search=_search_user_accounts,
    ),
)

NATIVE_BY_KEY = {source.key: source for source in NATIVE_SOURCES}


# --- external systems --------------------------------------------------
#
# Connector keys that have a DSAR search adapter written against them.
# Empty on purpose: adapters exist for syncing, not for locating one
# person's records on request, and declaring a capability that does not
# exist is exactly the failure this module was written to stop.
#
# Adding a real adapter means adding its connector key here and a
# searcher beside it. Nothing else in DSAR needs to change.
DSAR_SEARCH_ADAPTERS: dict[str, Searcher] = {}


async def connected_connectors(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, str]:
    """Which integrations this organization has actually configured.

    Returns connector key -> connection name. Read from the connection
    table rather than assumed, so a source is "connected" because
    somebody connected it.
    """
    from app.integrations.models import IntegrationConnection

    rows = (
        await db.execute(
            select(
                IntegrationConnection.connector_key, IntegrationConnection.name
            ).where(
                IntegrationConnection.organization_id == organization_id,
                # Anything else — error, disconnected, disabled — is not
                # something to promise a search against.
                IntegrationConnection.status.in_(("active", "connected")),
            )
        )
    ).all()
    return {key: name for key, name in rows}


def capability_for_system(
    *, name: str, connector_key: str | None, connected: dict[str, str]
) -> tuple[str, str]:
    """What can be done about one named system, and why.

    The order of the checks is the order the honesty degrades: a real
    adapter on a real connection, then a connection with no way to search
    it, then nothing at all.
    """
    if connector_key and connector_key in connected:
        if connector_key in DSAR_SEARCH_ADAPTERS:
            return (
                SEARCHABLE,
                f"{connected[connector_key]} is connected and can be searched directly.",
            )
        return (
            MANUAL_FOLLOW_UP,
            f"{connected[connector_key]} is connected, but Veyntra has no data-request "
            "search for it yet. Search it in the tool itself.",
        )
    return (
        NOT_CONNECTED,
        f"No Veyntra integration is configured for {name}. A person must search it "
        "or ask its owner.",
    )


def match_connector(name: str) -> str | None:
    """Guess which connector a named system corresponds to.

    Used only to *find* an existing connection, never to claim one:
    guessing wrong yields "not connected", which is the safe direction.
    The names come from the integrations package rather than a list
    invented here, so a new adapter is matchable the day it lands.
    """
    normalised = (name or "").strip().lower()
    if not normalised:
        return None
    for key in _known_connector_keys():
        if key in normalised or normalised in key:
            return key
    return None


def _known_connector_keys() -> tuple[str, ...]:
    """Connector keys the integrations package ships adapters for."""
    import pkgutil

    from app.integrations import adapters

    return tuple(
        module.name
        for module in pkgutil.iter_modules(adapters.__path__)
        if not module.name.startswith("_") and module.name not in ("base", "mock")
    )


__all__ = [
    "CAPABILITY_LABELS",
    "DSAR_SEARCH_ADAPTERS",
    "HIGH",
    "LOW",
    "MANUAL_FOLLOW_UP",
    "NATIVE_BY_KEY",
    "NATIVE_SOURCES",
    "NOT_CONNECTED",
    "POSSIBLE",
    "PROCESSOR_FOLLOW_UP",
    "RELEVANCE_LABELS",
    "RELEVANCE_ORDER",
    "SEARCHABLE",
    "UNSUPPORTED",
    "NativeSource",
    "capability_for_system",
    "connected_connectors",
    "match_connector",
]
