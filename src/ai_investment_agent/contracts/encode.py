"""Encode a local TradeProposal as a versioned envelope. Does not transmit."""

from __future__ import annotations

from typing import Literal

from ai_investment_agent.domain.envelope import TradeProposalEnvelope
from ai_investment_agent.domain.proposal import TradeProposal


def envelope_from_proposal(
    proposal: TradeProposal,
    *,
    market: Literal["KRX"] = "KRX",
) -> TradeProposalEnvelope:
    return TradeProposalEnvelope.from_proposal(proposal, market=market)
