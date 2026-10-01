"""Wire LIVE_OBSERVATION collectors. Never enables broker or order paths."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.llm import LiveLlmProvider
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.adapters.live.observation import (
    observation_capital_from_env,
    observation_portfolio_from_env,
    observation_risk_budgets,
)
from ai_investment_agent.adapters.live.scheduled import UnconfiguredScheduledEventCollector
from ai_investment_agent.analysis.clock import utc_now
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.domain.enums import DataMode
from ai_investment_agent.domain.runtime import RuntimeSettings

# LIVE never mixes fixture calendar rows, regardless of this leftover env name.
# 0 / 1 / unset all resolve to UnconfiguredScheduledEventCollector.
SCHEDULED_USE_FIXTURE_IGNORED_IN_LIVE = True


def live_observation_enabled() -> bool:
    return os.environ.get("AI_DATA_MODE", "FIXTURE").upper() == DataMode.LIVE_OBSERVATION.value


def build_live_observation_service(
    *,
    now_fn: Callable[[], datetime] | None = None,
    market: LiveMarketDataCollector | None = None,
    news: LiveNewsCollector | None = None,
    disclosure: LiveDisclosureCollector | None = None,
    macro: LiveMacroCollector | None = None,
) -> AnalysisService:
    """Construct AnalysisService on live collectors with observation capital context.

    Default clock is timezone-aware UTC now. Inject ``now_fn`` only for tests.
    Historical ``as_of`` is allowed as an analysis cutoff / query window.
    Newly fetched rows still stamp ``sourceReceivedAt`` with the actual
    receive clock — they are never backdated as if received at ``as_of``.

    Terminal artifact remains TradeProposal. Broker is never connected.
    ``SCHEDULED_USE_FIXTURE`` is ignored in LIVE so fixture calendar rows
    cannot mix into observation.
    """
    _ = os.environ.get("SCHEDULED_USE_FIXTURE")
    service = AnalysisService(
        now_fn=now_fn or utc_now,
        runtime=RuntimeSettings(data_mode=DataMode.LIVE_OBSERVATION),
    )
    service.market = market or LiveMarketDataCollector()
    service.news = news or LiveNewsCollector()
    service.disclosure = disclosure or LiveDisclosureCollector()
    service.macro = macro or LiveMacroCollector()
    service.scheduled = UnconfiguredScheduledEventCollector()
    service.default_capital = observation_capital_from_env()
    service.default_portfolio = observation_portfolio_from_env()
    service.default_risk_budgets = observation_risk_budgets()
    service.llm = LiveLlmProvider()
    return service
