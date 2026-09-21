"""TradeProposalEnvelope: producer-side contract. Not an order.

A future Auto-Trading-system may consume this JSON. This module does not
send it anywhere, call a broker, or share storage.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from ai_investment_agent.domain.base import DomainModel, to_camel
from ai_investment_agent.domain.enums import (
    Action,
    ConfidenceSource,
    EnvelopeArtifactType,
    Horizon,
)
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.domain.versions import TRADE_PROPOSAL_SCHEMA_VERSION


class EnvelopeThesis(DomainModel):
    """Contract-sized thesis. Not a broker memo or order comment."""

    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    bull_case: str
    bear_case: str
    drivers: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)

    @classmethod
    def from_thesis(cls, thesis: InvestmentThesis) -> EnvelopeThesis:
        return cls(
            headline=thesis.headline,
            summary=thesis.summary,
            bull_case=thesis.bull_case,
            bear_case=thesis.bear_case,
            drivers=list(thesis.drivers),
            invalidations=list(thesis.invalidations),
        )


class EnvelopeInvalidation(DomainModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @classmethod
    def from_condition(cls, item: InvalidationCondition) -> EnvelopeInvalidation:
        return cls(code=item.code, description=item.description)


class TradeProposalEnvelope(DomainModel):
    """Versioned judgment payload for a future consumer.

    suggestedCapitalPct remains a recommendation, not an order size.
    isOrder is always false and cannot be set true.
    """

    schema_version: Literal["ai.trade-proposal.v1"] = TRADE_PROPOSAL_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    generated_at: datetime
    ticker: str = Field(min_length=1)
    market: Literal["KRX"] = "KRX"
    horizon: Horizon
    action: Action
    confidence: float = Field(ge=0, le=1)
    confidence_source: ConfidenceSource
    expected_return: Decimal
    estimated_risk: Decimal = Field(ge=0)
    suggested_capital_pct: Decimal = Field(ge=0, le=100)
    thesis: EnvelopeThesis
    invalidation_conditions: list[EnvelopeInvalidation] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    artifact_type: Literal["TRADE_PROPOSAL"] = EnvelopeArtifactType.TRADE_PROPOSAL.value
    is_order: Literal[False] = False
    producer: Literal["ai_investment_agent"] = "ai_investment_agent"
    intended_consumer: Literal["future_auto_trading_system"] = "future_auto_trading_system"

    @model_validator(mode="after")
    def not_an_order_and_known_schema(self) -> TradeProposalEnvelope:
        if self.is_order:
            raise ValueError("TradeProposalEnvelope is not an order")
        if self.artifact_type != EnvelopeArtifactType.TRADE_PROPOSAL.value:
            raise ValueError("envelope artifactType must be TRADE_PROPOSAL")
        if self.schema_version != TRADE_PROPOSAL_SCHEMA_VERSION:
            raise ValueError("unsupported schemaVersion")
        if self.action in {Action.NO_TRADE, Action.TACTICAL_WAIT} and self.suggested_capital_pct != 0:
            raise ValueError("NO_TRADE and TACTICAL_WAIT must use suggestedCapitalPct=0")
        return self

    @classmethod
    def from_proposal(
        cls,
        proposal: TradeProposal,
        *,
        market: Literal["KRX"] = "KRX",
    ) -> TradeProposalEnvelope:
        if proposal.calibrated_confidence is not None:
            confidence = proposal.calibrated_confidence
            source = ConfidenceSource.CALIBRATED
        else:
            confidence = proposal.raw_confidence
            source = ConfidenceSource.RAW
        return cls(
            schema_version=TRADE_PROPOSAL_SCHEMA_VERSION,
            proposal_id=proposal.decision_id,
            generated_at=proposal.generated_at,
            ticker=proposal.ticker,
            market=market,
            horizon=proposal.horizon,
            action=proposal.action,
            confidence=confidence,
            confidence_source=source,
            expected_return=proposal.expected_return,
            estimated_risk=proposal.estimated_risk,
            suggested_capital_pct=proposal.suggested_capital_pct,
            thesis=EnvelopeThesis.from_thesis(proposal.thesis),
            invalidation_conditions=[
                EnvelopeInvalidation.from_condition(item) for item in proposal.invalidation_conditions
            ],
            reason_codes=list(proposal.reason_codes),
            model_version=proposal.model_version,
            feature_version=proposal.feature_version,
            policy_version=proposal.policy_version,
        )

    @property
    def idempotency_key(self) -> str:
        return self.proposal_id


class ConsumerTradeProposalEnvelope(TradeProposalEnvelope):
    """Future-consumer parse mode: ignore additive unknown fields.

    Still rejects an unknown schemaVersion. This parser is not a live
    Auto-Trading-system client.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="ignore",
        str_strip_whitespace=True,
    )
