from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from ai_investment_agent.adapters.fixtures.llm import FixtureLlmProvider
from ai_investment_agent.adapters.fixtures.market import (
    FixtureEventProvider,
    FixtureMarketDataProvider,
)
from ai_investment_agent.adapters.in_memory import (
    InMemoryDecisionPublisher,
    InMemoryDecisionRepository,
)
from ai_investment_agent.agents.judgment_agent import JudgmentAgent
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import DecisionType

FIXED_NOW = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def provided_capital() -> CapitalContext:
    return CapitalContext(
        total_capital=Decimal("100000000"),
        ai_capital_limit=Decimal("10000000"),
        ai_capital_ratio=Decimal("0.10"),
        long_term_budget=Decimal("7000000"),
        short_term_budget=Decimal("3000000"),
        reserve_cash=Decimal("20000000"),
        risk_budget=Decimal("5000000"),
        source="provided",
    )


def make_agent(
    market_file: str,
    desired: DecisionType = DecisionType.LONG_TERM_BUY,
    event_provider: FixtureEventProvider | None = None,
) -> tuple[JudgmentAgent, InMemoryDecisionRepository, InMemoryDecisionPublisher]:
    market = FixtureMarketDataProvider.from_files(market_file)
    events = event_provider or FixtureEventProvider.from_file("events.json")
    llm = FixtureLlmProvider(desired=desired, raw_confidence=0.72)
    repository = InMemoryDecisionRepository()
    publisher = InMemoryDecisionPublisher()
    agent = JudgmentAgent(
        market_data=market,
        events=events,
        llm=llm,
        repository=repository,
        publisher=publisher,
        now_fn=lambda: FIXED_NOW,
    )
    return agent, repository, publisher
