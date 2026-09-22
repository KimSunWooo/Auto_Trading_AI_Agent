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
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.collectors.intelligence import FixtureScheduledEventCollector
from ai_investment_agent.domain.enums import DataMode
from ai_investment_agent.domain.runtime import RuntimeSettings


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

    Terminal artifact remains TradeProposal. Broker is never connected.
    """
    service = AnalysisService(
        now_fn=now_fn,
        runtime=RuntimeSettings(data_mode=DataMode.LIVE_OBSERVATION),
    )
    service.market = market or LiveMarketDataCollector()
    service.news = news or LiveNewsCollector()
    service.disclosure = disclosure or LiveDisclosureCollector()
    service.macro = macro or LiveMacroCollector()
    # Scheduled calendar remains fixture unless a live calendar provider is configured later.
    if os.environ.get("SCHEDULED_USE_FIXTURE", "1") == "1":
        service.scheduled = FixtureScheduledEventCollector.from_file()
    service.default_capital = observation_capital_from_env()
    service.default_portfolio = observation_portfolio_from_env()
    service.default_risk_budgets = observation_risk_budgets()
    service.llm = LiveLlmProvider()
    return service
