from ai_investment_agent.adapters.fixtures.portfolio import fixture_capital
from ai_investment_agent.analysis.service import AnalysisService, merge_external_status
from ai_investment_agent.collectors.intelligence import (
    FixtureDisclosureCollector,
    FixtureMacroCollector,
    FixtureNewsCollector,
    FixtureScheduledEventCollector,
)
from ai_investment_agent.collectors.market import FixtureMarketDataCollector
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import (
    Action,
    CollectionStatus,
    DataMode,
    DecisionReadinessStatus,
    EntryTiming,
    ReasonCode,
)
from ai_investment_agent.domain.policy import PortfolioContext, RiskBudgets
from ai_investment_agent.domain.runtime import RuntimeSettings
from tests.horizon_support import (
    AS_OF,
    bullish_long,
    bullish_short,
    good_entry,
    judge,
    weak_long,
    weak_short,
)


def test_missing_entry_forbids_buy_now_on_bullish_long():
    snapshot = judge(long_features=bullish_long(), short_features=weak_short(), entry=None)
    assert snapshot.horizon_decision.entry_timing is EntryTiming.WAIT
    assert snapshot.proposal.action is not Action.BUY
    assert ReasonCode.ENTRY_CONTEXT_MISSING.value in snapshot.proposal.reason_codes


def test_missing_entry_forbids_buy_now_on_bullish_short():
    snapshot = judge(long_features=weak_long(), short_features=bullish_short(), entry=None)
    assert snapshot.horizon_decision.entry_timing is EntryTiming.WAIT
    assert snapshot.proposal.action is not Action.BUY
    assert ReasonCode.ENTRY_CONTEXT_MISSING.value in snapshot.proposal.reason_codes


def test_missing_capital_forbids_buy():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
        capital_context=CapitalContext.missing_conservative(),
    )
    assert snapshot.proposal.action is not Action.BUY
    assert snapshot.proposal.suggested_capital_pct == 0
    codes = snapshot.proposal.reason_codes
    assert (
        ReasonCode.CAPITAL_CONTEXT_MISSING.value in codes
        or ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value in codes
    )


def test_live_profile_missing_portfolio_forbids_buy():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
        data_mode=DataMode.LIVE_OBSERVATION,
        portfolio_context=None,
        risk_budgets=RiskBudgets.fixture_open(),
    )
    assert snapshot.proposal.action is not Action.BUY
    assert ReasonCode.PORTFOLIO_CONTEXT_MISSING.value in snapshot.proposal.reason_codes


def test_live_profile_missing_risk_budgets_forbids_buy():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
        data_mode=DataMode.LIVE_SHADOW,
        portfolio_context=PortfolioContext.fixture_empty(),
        risk_budgets=None,
    )
    assert snapshot.proposal.action is not Action.BUY
    assert ReasonCode.RISK_BUDGETS_MISSING.value in snapshot.proposal.reason_codes


def test_market_data_unavailable_forbids_buy():
    service = AnalysisService()
    service.market = FixtureMarketDataCollector(records=[], unavailable=True)
    result = service.evaluate("005930", capital_context=fixture_capital())
    assert result.market_status is CollectionStatus.DATA_UNAVAILABLE
    assert result.readiness is not None
    assert result.readiness.status is DecisionReadinessStatus.BLOCKED
    assert result.readiness.allows_new_buy is False
    assert result.action is not Action.BUY
    assert ReasonCode.MARKET_DATA_UNAVAILABLE.value in result.readiness.reason_codes


def test_market_data_stale_forbids_buy():
    service = AnalysisService()
    ok = service.market.collect("005930", AS_OF)
    stale_items = ok.items

    class _Stale:
        def collect(self, instrument, as_of, kinds=None):
            return CollectionResult.stale(stale_items, as_of=as_of, stale_item_ids=["stale"])

    service.market = _Stale()
    result = service.evaluate("005930", capital_context=fixture_capital())
    assert result.market_status is CollectionStatus.STALE
    assert result.readiness is not None
    assert result.readiness.allows_new_buy is False
    assert result.action is not Action.BUY
    assert ReasonCode.MARKET_DATA_STALE.value in result.readiness.reason_codes


def test_partial_external_outage_is_not_overall_healthy():
    as_of = AS_OF
    news = FixtureNewsCollector.from_file().collect("005930", as_of)
    scheduled = FixtureScheduledEventCollector.from_file().collect(as_of, ticker="005930")
    disclosure = CollectionResult.unavailable(error="disclosure feed down", as_of=as_of)
    macro = CollectionResult.unavailable(error="macro feed down", as_of=as_of)
    status, error = merge_external_status(
        {
            "news": news,
            "disclosure": disclosure,
            "macro": macro,
            "scheduledEvent": scheduled,
        }
    )
    assert status is CollectionStatus.DEGRADED
    assert status is not CollectionStatus.OK
    assert error is not None
    assert "disclosure" in error
    assert "macro" in error

    service = AnalysisService()
    service.disclosure = FixtureDisclosureCollector(records=[], unavailable=True)
    service.macro = FixtureMacroCollector(records=[], unavailable=True)
    result = service.evaluate("005930", capital_context=fixture_capital())
    names = {item.name: item.status for item in result.provider_health}
    assert names["disclosure"] is CollectionStatus.DATA_UNAVAILABLE
    assert names["macro"] is CollectionStatus.DATA_UNAVAILABLE
    assert result.external_status is CollectionStatus.DEGRADED
    assert result.readiness is not None
    assert result.readiness.status is not DecisionReadinessStatus.READY
    assert result.readiness.allows_new_buy is False
    assert result.action is not Action.BUY


def test_no_event_is_not_data_unavailable():
    quiet = FixtureNewsCollector(records=[]).collect("005930", AS_OF)
    failed = FixtureNewsCollector(records=[], unavailable=True).collect("005930", AS_OF)
    assert quiet.status is CollectionStatus.NO_EVENT
    assert failed.status is CollectionStatus.DATA_UNAVAILABLE
    assert quiet.status is not failed.status


def test_fixture_profile_with_explicit_contexts_can_buy():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
        data_mode=DataMode.FIXTURE,
        capital_context=fixture_capital(),
        portfolio_context=PortfolioContext.fixture_empty(),
        risk_budgets=RiskBudgets.fixture_open(),
    )
    assert snapshot.proposal.action is Action.BUY
    assert snapshot.proposal.data_mode is DataMode.FIXTURE


def test_analysis_service_does_not_invent_fixture_capital():
    result = AnalysisService().evaluate("005930")
    assert result.snapshot.capital_context.source == "missing_conservative_default"
    assert result.action is not Action.BUY
    result_with_capital = AnalysisService().evaluate(
        "005930", capital_context=fixture_capital()
    )
    assert result_with_capital.snapshot.capital_context.source == "provided"
    assert result_with_capital.data_mode is DataMode.FIXTURE
    assert result_with_capital.orders_placed == 0


def test_missing_runtime_profile_is_never_live():
    service = AnalysisService()
    assert service.runtime.data_mode is DataMode.FIXTURE
    live = AnalysisService(runtime=RuntimeSettings(data_mode=DataMode.LIVE_OBSERVATION))
    assert live.runtime.is_live_compatible is True
    assert live.runtime.allows_fixture_fallback is False
