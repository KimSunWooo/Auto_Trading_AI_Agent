from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import JournalStage


class DecisionJournalEntry(DomainModel):
    journal_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    stage: JournalStage
    message: str
    reason_codes: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime
