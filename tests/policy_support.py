from datetime import datetime, timezone
from decimal import Decimal

from ai_investment_agent.domain.enums import Action, Horizon, MarketRegimeType
from ai_investment_agent.domain.market import MarketRegime
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.policy.safety import SafetyPolicyLayer
from tests.support import provided_capital

AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
LAYER = SafetyPolicyLayer()


def buy_proposal(
    *,
    ticker: str = "005930",
    pct: Decimal = Decimal("50"),
    horizon: Horizon = Horizon.LONG_TERM,
    estimated_risk: Decimal = Decimal("0.02"),
) -> TradeProposal:
    return TradeProposal(
        decision_id="dec_" + "c" * 32,
        ticker=ticker,
        horizon=horizon,
        action=Action.BUY,
        raw_confidence=0.7,
        calibrated_confidence=0.7,
        expected_return=Decimal("0.06"),
        estimated_risk=estimated_risk,
        suggested_capital_pct=pct,
        expected_holding_period=252 if horizon is Horizon.LONG_TERM else 5,
        thesis=InvestmentThesis(
            headline="policy fixture",
            summary="Used only by the safety layer tests.",
            bull_case="bull",
            bear_case="bear",
            time_horizon=horizon,
        ),
        invalidation_conditions=[
            InvalidationCondition(code="X", description="break if X")
        ],
        reason_codes=["FIXTURE_DECISION"],
        market_regime=MarketRegime(
            regime=MarketRegimeType.SIDEWAYS,
            confidence=0.6,
            as_of=AS_OF,
            explanation="fixture",
        ),
        generated_at=AS_OF,
    )


def sell_proposal() -> TradeProposal:
    return buy_proposal(pct=Decimal("0")).model_copy(
        update={
            "action": Action.SELL,
            "horizon": Horizon.NONE,
            "expected_holding_period": 0,
            "expected_return": Decimal("0"),
            "suggested_capital_pct": Decimal("0"),
        }
    )


def apply(proposal: TradeProposal, **kwargs):
    return LAYER.apply(
        proposal,
        capital=kwargs.pop("capital", provided_capital()),
        **kwargs,
    )
