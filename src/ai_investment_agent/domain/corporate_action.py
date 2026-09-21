from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.collection import CollectionTimestamps
from ai_investment_agent.domain.enums import CorporateActionType, FreshnessClass


class CorporateAction(DomainModel):
    """Corporate action. Fixture domain only; no live vendor feed."""

    action_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    action_type: CorporateActionType
    timestamps: CollectionTimestamps
    freshness_class: FreshnessClass = FreshnessClass.LONG_HORIZON
    ex_date: date | None = None
    effective_date: date | None = None
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    currency: str | None = None
    new_ticker: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    source: str = "fixture"
    raw_ref: str | None = None
