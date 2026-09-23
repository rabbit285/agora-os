"""When something moves underneath a transfer somebody already approved.

A transfer record is a judgement: this recipient, in this country, is
covered by this mechanism. The judgement was sound when it was made. Then
the vendor record changes country, or the DPA behind it is replaced, and
the judgement may no longer hold — not because anyone was careless, but
because the thing it was about moved.

One rule governs everything here.

**A flag is not an edit.** Nothing in this module changes a destination,
a mechanism, or a safeguard. It writes `review_reason` and stops. A
transfer assessed against Ireland does not silently become a transfer
assessed against Virginia because a vendor row was updated — that would
turn one person's approval into cover for a decision they never saw. The
approval belongs to whoever gave it, so the product asks them again
instead of answering for them.

The checks are deliberately narrow. Each compares two recorded facts and
fires only when they disagree; none of them infer, and none of them fire
on absence. A vendor with no country recorded raises nothing, because
"we did not write it down" is not evidence the data moved.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import DataTransfer, Vendor

# A transfer nobody is relying on any more does not need re-approval.
_LIVE = ("active", "under_review")


def _country_moved(transfer: DataTransfer, vendor: Vendor) -> str | None:
    """The vendor's recorded location no longer matches the transfer's.

    The case where being wrong matters most: the mechanism was chosen for
    a destination, and the destination is now recorded differently. An
    adequacy decision covering one country says nothing about another.
    """
    recorded = (vendor.country or "").strip().upper()
    declared = (transfer.destination_country or "").strip().upper()
    # No recorded country is missing information, not a move.
    if not recorded or recorded == declared:
        return None
    return (
        f"{vendor.name}'s recorded location changed to {recorded}; this "
        f"transfer was assessed against {declared}. A mechanism approved "
        f"for {declared} does not automatically cover {recorded}."
    )


def _dpa_not_in_place(transfer: DataTransfer, vendor: Vendor) -> str | None:
    """The agreement the transfer leans on is not on file.

    Only fires where the mechanism actually depends on the contract —
    SCCs are a contractual instrument, so the absence of a signed DPA
    undercuts them. An adequacy decision does not rest on the vendor's
    paperwork, and flagging it there would be noise.

    `not_required` is a decision somebody made and is left alone;
    `pending` is the case worth raising, because the transfer is
    recorded as covered by a contract nobody has signed.
    """
    if (transfer.transfer_mechanism or "").strip().lower() != "sccs":
        return None
    if (vendor.dpa_status or "").strip().lower() != "pending":
        return None
    return (
        f"This transfer relies on standard contractual clauses, and "
        f"{vendor.name}'s DPA is still recorded as pending. The mechanism "
        "may not be in place."
    )


_CHECKS = (_country_moved, _dpa_not_in_place)


async def flag_drifted_transfers(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DataTransfer]:
    """Stamp `review_reason` on transfers whose underlying facts moved.

    Returns the transfers it flagged. Safe to call on every read: it is
    idempotent, it writes only when the reason text would change, and it
    never touches a transfer's substance.
    """
    rows = (
        await db.execute(
            select(DataTransfer, Vendor)
            .join(Vendor, Vendor.id == DataTransfer.vendor_id)
            .where(
                DataTransfer.organization_id == organization_id,
                DataTransfer.vendor_id.is_not(None),
                DataTransfer.status.in_(_LIVE),
            )
        )
    ).all()

    flagged: list[DataTransfer] = []
    changed = False
    for transfer, vendor in rows:
        reasons = [reason for check in _CHECKS if (reason := check(transfer, vendor))]
        reason = " ".join(reasons) if reasons else None

        # Clearing matters as much as setting: once the vendor record and
        # the transfer agree again, a stale flag would ask a person to
        # re-review something that no longer differs.
        if transfer.review_reason != reason:
            transfer.review_reason = reason
            changed = True
        if reason:
            flagged.append(transfer)

    if changed:
        await db.commit()
    return flagged


__all__ = ["flag_drifted_transfers"]
