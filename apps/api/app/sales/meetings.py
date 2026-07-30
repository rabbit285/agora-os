"""Meeting Assistant (spec §26) — real retrieval-grounded prep notes via
the existing AI Copilot, not a canned template. If the org's knowledge
base has nothing relevant, `ask_copilot` already returns an honest
no-evidence message (see `app.ai.copilot.NO_EVIDENCE_MESSAGE`) rather than
a hallucinated briefing — this module inherits that behavior for free by
calling the same function every other grounded feature uses.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import ask_copilot
from app.sales.models import Account, Meeting


async def generate_prep_notes(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    meeting: Meeting,
    account: Account | None,
    requested_by: uuid.UUID | None,
) -> str:
    subject = account.name if account else meeting.title
    question = (
        f"Prepare briefing notes for an upcoming sales meeting titled "
        f'"{meeting.title}" with {subject}. Summarize anything in our '
        "knowledge base relevant to this account or opportunity, including "
        "past interactions, product fit, and open risks."
    )
    answer = await ask_copilot(
        db, organization_id=organization_id, requested_by=requested_by, question=question
    )
    return answer.text
