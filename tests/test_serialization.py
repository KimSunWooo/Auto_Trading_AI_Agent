from decimal import Decimal

from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import Action, Horizon, JournalStage, MarketRegimeType
from ai_investment_agent.domain.journal import DecisionJournalEntry
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.serialization import from_json, to_dict, to_json
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from tests.support import FIXED_NOW, provided_capital


def _proposal() -> TradeProposal:
    regime = MarketRegime(
        regime=MarketRegimeType.SIDEWAYS,
        confidence=0.6,
        as_of=FIXED_NOW,
        explanation="fixture",
    )
    return TradeProposal(
        decision_id="dec_" + "a" * 32,
        ticker="005930",
        horizon=Horizon.LONG_TERM,
        action=Action.BUY,
        raw_confidence=0.7,
        calibrated_confidence=0.7,
        expected_return=Decimal("0.06"),
        estimated_risk=Decimal("0.18"),
        suggested_capital_pct=Decimal("5"),
        expected_holding_period=252,
        thesis=InvestmentThesis(
            headline="Roundtrip thesis",
            summary="Used only to verify serialization.",
            bull_case="bull",
            bear_case="bear",
            time_horizon=Horizon.LONG_TERM,
        ),
        invalidation_conditions=[
            InvalidationCondition(code="X", description="break if X")
        ],
        reason_codes=["FIXTURE_DECISION"],
        market_regime=regime,
        generated_at=FIXED_NOW,
    )


def test_trade_proposal_json_roundtrip_uses_camel_case():
    proposal = _proposal()
    raw = to_json(proposal)
    assert '"decisionId"' in raw
    assert '"suggestedCapitalPct"' in raw
    assert '"rawConfidence"' in raw
    restored = from_json(TradeProposal, raw)
    assert restored == proposal
    assert restored.decision.value == "LONG_TERM_BUY"


def test_capital_context_json_roundtrip():
    capital = provided_capital()
    restored = from_json(CapitalContext, to_json(capital))
    assert restored == capital
    assert '"aiCapitalLimit"' in to_json(capital)


def test_decision_snapshot_and_journal_roundtrip():
    proposal = _proposal()
    snapshot = DecisionSnapshot(
        decision_id=proposal.decision_id,
        ticker=proposal.ticker,
        market_snapshot=MarketSnapshot(
            ticker="005930",
            as_of=FIXED_NOW,
            last_price=Decimal("71000"),
            data_completeness=Decimal("0.95"),
            regime_hint=MarketRegimeType.SIDEWAYS,
        ),
        events=[
            MarketEvent(
                event_id="evt_1",
                ticker="005930",
                event_type="MACRO",
                title="fixture",
                occurred_at=FIXED_NOW,
            )
        ],
        market_regime=proposal.market_regime,
        capital_context=provided_capital(),
        thesis=proposal.thesis,
        proposal=proposal,
        created_at=FIXED_NOW,
    )
    restored = from_json(DecisionSnapshot, to_json(snapshot))
    assert restored.proposal.decision_id == snapshot.decision_id
    assert restored.capital_context.ai_capital_limit == Decimal("10000000")
    as_dict = to_dict(snapshot)
    assert "marketSnapshot" in as_dict
    assert "capitalContext" in as_dict

    entry = DecisionJournalEntry(
        journal_id="jnl_" + "b" * 32,
        decision_id=proposal.decision_id,
        stage=JournalStage.DECISION,
        message="recorded",
        recorded_at=FIXED_NOW,
    )
    assert from_json(DecisionJournalEntry, to_json(entry)) == entry
