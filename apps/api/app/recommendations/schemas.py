from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class RecommendationOut(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    business_impact: str
    reason: str
    sources: list[str]
    confidence: str
    estimated_value: str | None
    suggested_action: str
    risk: str
    required_approval: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
