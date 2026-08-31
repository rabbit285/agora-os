"""When a data request is actually due.

The response window is **one month from receipt**, not thirty days. Those
are different dates for most of the year and the difference is not
academic: a request received on 31 January is due on 28 February, and a
product that adds thirty days answers on 2 March — two days into a missed
statutory deadline, while its own screen says the request is on time.

A calendar month also has to survive the short ones. "One month after 31
January" is a date that does not exist, so it clamps to the last day of
the target month, which is the convention every supervisory authority
publishes and the only one that never lands outside the month it names.

Extensions are modelled rather than mentioned. A controller may extend
by two further months where a request is complex, and that is a decision
somebody makes and records — not a longer default. The effective
deadline is the extension where one was granted and the base deadline
otherwise, so nothing downstream has to know which case it is looking at.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

# How far ahead a request counts as "due soon" on the overview and in the
# review queue. A week is long enough to act on and short enough that the
# list stays worth reading.
DUE_SOON_DAYS = 7

# The maximum further extension a controller can record. Two months, on
# top of the initial one — the limit the GDPR sets for complex or
# numerous requests.
MAX_EXTENSION_MONTHS = 2


def as_utc(moment: datetime) -> datetime:
    """A timezone-aware moment, whatever the driver handed back.

    Columns are declared `DateTime(timezone=True)`, but not every
    backend returns an aware value — SQLite does not — and comparing a
    naive datetime with an aware one raises rather than answering
    wrongly. A stored timestamp is UTC by construction here, so reading
    it as UTC is a statement of what it already is, not a conversion.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def add_months(moment: datetime, months: int) -> datetime:
    """The same day-of-month, `months` later, clamped to a real date.

    31 January + 1 month is 28 February (29 in a leap year), because
    31 February is not a date. Time of day is preserved so a deadline
    keeps the hour the request arrived.
    """
    moment = as_utc(moment)
    total = moment.month - 1 + months
    year = moment.year + total // 12
    month = total % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def response_due(received_at: datetime, *, extension_months: int = 0) -> datetime:
    """The deadline for responding to a request received at this moment."""
    return add_months(received_at, 1 + max(0, extension_months))


@dataclass
class DeadlineState:
    """Where a request stands against its deadline, in one place.

    Derived rather than stored: a stored "overdue" flag is wrong from the
    moment the clock passes it and nobody has run a job.
    """

    due_at: datetime
    # The base deadline, kept separate so the screen can say "extended to"
    # rather than silently showing a later date as though it were always
    # the deadline.
    base_due_at: datetime
    extended: bool
    extension_months: int
    days_remaining: int
    overdue: bool
    due_soon: bool
    label: str


def _now() -> datetime:
    return datetime.now(UTC)


def describe(
    *,
    received_at: datetime,
    extension_months: int = 0,
    completed_at: datetime | None = None,
    now: datetime | None = None,
) -> DeadlineState:
    """The deadline, and how a person should read it.

    A completed request is never overdue. It was answered; whether it was
    answered late is a fact about the response, not a thing to keep
    flashing on a worklist forever.
    """
    moment = as_utc(now or _now())
    received_at = as_utc(received_at)
    completed_at = as_utc(completed_at) if completed_at else None
    base = response_due(received_at)
    due = response_due(received_at, extension_months=extension_months)
    remaining = (due.date() - moment.date()).days
    done = completed_at is not None
    overdue = not done and moment > due
    due_soon = not done and not overdue and 0 <= remaining <= DUE_SOON_DAYS

    if done:
        label = "Completed"
    elif overdue:
        late = abs(remaining)
        label = f"Overdue by {late} day{'' if late == 1 else 's'}"
    elif remaining == 0:
        label = "Due today"
    elif remaining == 1:
        label = "Due tomorrow"
    else:
        label = f"Due in {remaining} days"

    return DeadlineState(
        due_at=due,
        base_due_at=base,
        extended=extension_months > 0,
        extension_months=extension_months,
        days_remaining=remaining,
        overdue=overdue,
        due_soon=due_soon,
        label=label,
    )


def clamp_extension(months: int) -> int:
    """An extension the product will record.

    Refusing a longer one here rather than at the screen means the
    boundary is in one place, and a request cannot be given four months
    by an API call that skipped the form.
    """
    return max(0, min(int(months), MAX_EXTENSION_MONTHS))


def days_until(moment: datetime | None, *, now: datetime | None = None) -> int | None:
    """Whole days from now until `moment`, negative once it has passed."""
    if moment is None:
        return None
    reference = as_utc(now or _now())
    return (as_utc(moment).date() - reference.date()).days


def next_review_from(moment: datetime | None = None, *, months: int = 12) -> datetime:
    """When a record should next be looked at.

    Twelve months by default because that is the cadence the rest of the
    product already uses for policy review, not because a regulation
    names a number — nothing requires an annual RoPA review, and the
    field exists so an organization can hold itself to a schedule.
    """
    return add_months(moment or _now(), months)


__all__ = [
    "DUE_SOON_DAYS",
    "MAX_EXTENSION_MONTHS",
    "DeadlineState",
    "add_months",
    "as_utc",
    "clamp_extension",
    "days_until",
    "describe",
    "next_review_from",
    "response_due",
]
