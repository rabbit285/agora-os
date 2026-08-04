from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class BriefingItemOut(BaseModel):
    text: str
    link: str | None


class BriefingSectionOut(BaseModel):
    key: str
    label: str
    headline: str
    items: list[BriefingItemOut]


class BriefingOut(BaseModel):
    id: uuid.UUID
    briefing_date: date
    sections: list[BriefingSectionOut]
    ai_suggestion: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
